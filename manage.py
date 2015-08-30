#!/usr/bin/env python
# -*- coding: utf8 -*-

import datetime
import os
import locale
import random
import paho.mqtt.client as mqtt

from flask import Flask
from flask.ext.script import Manager
from flask.ext.mail import Mail, Message
from sqlalchemy.sql import func

prod = '/var/www/vvm.hanse.de/wsgi/vvmroster/production.cfg'
dev = os.getcwd() + '/dev.cfg'

os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = '/dev/null'
if os.path.exists(prod):
	os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = prod
elif os.path.exists(dev):
	os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = dev

import vvmroster

locale.setlocale(locale.LC_ALL, vvmroster.app.config['LOCALE'])

manager = Manager(vvmroster.app)
mail = Mail(vvmroster.app)


@manager.command
def sendNagMail():
	"Sends out an email if the minimum number of volunteers has not been met"
	day = vvmroster.currentDay()
	dayFormatted = day.strftime('%A, %d. %B')
	counts = vvmroster.Roster.getCountsForSundays([day])
	if counts[0]['count'] >= 1:
		return
	text = '''Liebe Kollegen,

am kommenden {day} fehlt in Aumühle noch Unterstützung! Damit wir
unseren Besuchern einen angenehmen Tag bereiten können, sollten mindestens zwei
von uns vor Ort sein. Die bisherigen Meldungen:
  Öffnen:    {counts[sum_open]}
  Betreuen:  {counts[sum_service]}
  Schließen: {counts[sum_close]}

Wenn ihr am Sonntag unterstützen könnt, meldet euch bitte unter
{url} an!


Mit freundlichen Grüßen,
Der Dienstplaner
'''
	text = text.format(day=dayFormatted, counts=counts[0],
		url=vvmroster.url_for('index', _external=True))
	#print text
	msg = Message(body=text,
		subject="Verstärkung am Sonntag in Aumühle benötigt!",
		sender=vvmroster.app.config['DEFAULT_MAIL_SENDER'],
		reply_to=vvmroster.app.config['NAG_EMAIL_REPLYTO'],
		recipients=vvmroster.app.config['NAG_EMAIL_RECIPIENTS'])
	mail.send(msg)


@manager.command
def printurl():
	print vvmroster.url_for('index', _external=True)


@manager.command
def filldb():
	"adds a bunch of users and roster entries"
	vvmroster.initdb()
	random.seed()
	admin_role = vvmroster.Role.query.filter_by(name='admin').first()
	sunday = vvmroster.currentDay()
	for i in range(50):
		user = vvmroster.user_datastore.create_user(name='User {}'.format(i),
			email='user{}@example.com'.format(i),
			password=vvmroster.encrypt_password('password'), roles=[])
		days = list((sunday + datetime.timedelta(days=i*7)) for i in range(0,6))
		for day in random.sample(days, 2):
			r = vvmroster.Roster()
			r.day = day
			r.user = user
			r.will_open = random.randint(0,1)
			r.will_service = random.randint(0,1)
			r.will_close = random.randint(0,1)
			r.comment = ""
			vvmroster.db.session.add(r)
	vvmroster.db.session.commit()


@manager.command
def getsums():
	"gets some sums from the roster"

	for r in vvmroster.Roster.getCountsForSundays(days=vvmroster.upcomingDays()):
		print r


@manager.command
def deleteOld():
	"deletes roster entries older than the current Sunday"
	query = vvmroster.Roster.query.filter(vvmroster.Roster.day < vvmroster.currentDay())
	print "deleted {:d} rows".format(query.delete())


@manager.command
def initdb():
	"creates the database and fills it with some demo data"
	vvmroster.initdb()


def updateVisitorCounter_connect(client, userdata, flags, rc):
	client.subscribe("/vvm/visitorcounter/#")


def updateVisitorCounter_message(client, userdata, msg):
	if msg.topic.endswith("/uptime"):
		userdata['uptime'] = msg.payload
	if msg.topic.endswith("/counter"):
		userdata['counter'] = msg.payload
	if userdata['uptime'] != 0 and userdata['counter'] != 0:
		userdata['run'] = False


@manager.command
def updateVisitorCounter():
	'''
	Queries the current counter value from the MQTT broker and saves it to the
	database.  The timestamp is clamped to the full hour on the assumption that
	we want one count per hour, and this command is called from cron every hour,
	on the hour.
	'''
	userdata = { 'counter': 0, 'uptime': 0, 'run': True }
	now = datetime.datetime.now()
	client = mqtt.Client("vvmweb", userdata = userdata)
	client.on_connect = updateVisitorCounter_connect
	client.on_message = updateVisitorCounter_message
	client.username_pw_set('vvmweb', 'EyPa7KAPvR9u')
	client.connect("vvm.hanse.de", 1883, 60)
	while (userdata['run']):
		client.loop(timeout=5)
		if (datetime.datetime.now() - now).total_seconds() > 60:
			print "no messages from broker in 60 seconds"
			client.disconnect()
			return
	client.disconnect()
	now = datetime.datetime.now()
	now = now.replace(minute=0, second=0, microsecond=0)
	vc = vvmroster.VisitorCounter(now, userdata['counter'], userdata['uptime'])
	vvmroster.db.session.add(vc)
	vvmroster.db.session.commit()


if __name__ == "__main__":
    manager.run()

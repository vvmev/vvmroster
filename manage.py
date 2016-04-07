#!/usr/bin/env python
# -*- coding: utf8 -*-

import datetime
import os
import locale
import random
import re
import paho.mqtt.client as mqtt
import sqlalchemy
import xlsxwriter

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

	print "Creating 50 users with random entries"
	for i in range(50):
		try:
			user = vvmroster.user_datastore.create_user(name='User {}'.format(i),
				email='user{}@example.com'.format(i),
				password=vvmroster.encrypt_password('password'), roles=[])
			vvmroster.db.session.commit()
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
		except sqlalchemy.exc.IntegrityError:
			vvmroster.db.session.rollback()
			pass
	vvmroster.db.session.commit()

	print "Creating visitor counter entries for the past three weeks"
	start = sunday - datetime.timedelta(21)
	start = start.replace(hour=0, minute=0, second=0, microsecond=0)
	counter = 123
	for d in range((datetime.datetime.now() - start).days + 1):
		for h in range(24):
			counter += random.randint(0, 10 if 11 <= h <= 17 else 1)
			day = start + datetime.timedelta(days=d, hours=h)
			vc = vvmroster.VisitorCounter(day, counter, 1)
			vvmroster.db.session.add(vc)
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
	if rc != 0:
		userdata['run'] = False
		print "unable to connect to broker"
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
	client = mqtt.Client(userdata = userdata)
	client.on_connect = updateVisitorCounter_connect
	client.on_message = updateVisitorCounter_message
	client.username_pw_set(vvmroster.app.config['VISITORCOUNTER_USER'],
			vvmroster.app.config['VISITORCOUNTER_PASS'])
	client.connect(vvmroster.app.config['VISITORCOUNTER_BROKER'], 1883, 60)
	while (userdata['run']):
		client.loop(timeout=5)
		if (datetime.datetime.now() - now).total_seconds() > 60:
			print "no messages from broker in 60 seconds"
			userdata['run'] = False
	client.disconnect()
	if userdata['uptime'] == 0 or userdata['counter'] == 0:
		return
	now = datetime.datetime.now()
	now = now.replace(minute=0, second=0, microsecond=0)
	vc = vvmroster.VisitorCounter(now, userdata['counter'], userdata['uptime'])
	vvmroster.db.session.add(vc)
	vvmroster.db.session.commit()


@manager.command
def rollupVisitorCounts():
	'''
	Fill the rollup table visitorcounts_perday based on visitorcounter values.
	'''
	# start should be the highest ts fom VisitorCountsPerDay, end should be
	# the highest ts from VisitorCounter.

	VisitorCounter = vvmroster.VisitorCounter
	VisitorCountPerHour = vvmroster.VisitorCountPerHour
	start = VisitorCountPerHour.query.order_by(VisitorCountPerHour.ts.desc()).first()
	if not start:
		start = VisitorCounter.query.order_by(VisitorCounter.ts).first()
	end = VisitorCounter.query.order_by(VisitorCounter.ts.desc()).first()
	start = start.ts
	end = end.ts
	print "rolling up entries from {} to {}".format(start.strftime("%Y-%m-%d"),
		end.strftime("%Y-%m-%d"))

	results = VisitorCounter.query.filter(VisitorCounter.ts >= start,
										  VisitorCounter.ts < end)\
								   .order_by(VisitorCounter.ts)\
								   .all()
	vcbyts = {}
	for result in results:
		vcbyts[result.ts] = result.vc
	ts = start
	counter = results[0].vc
	while ts <= end:
		if ts in vcbyts:
			count = vcbyts[ts] - counter
			counter = vcbyts[ts]
		else:
			count = 0
		vc = vvmroster.VisitorCountPerHour(ts, count)
		vvmroster.db.session.add(vc)
		if ts.hour == 23:
			vvmroster.db.session.commit()
		ts += datetime.timedelta(hours=1)
	pass


@manager.command
def exportVisitorCounter(file="visitorcounter.xlsx", start=None, end=None):
	'''
	Export all visitor counter entries into an Excel sheet.
	'''
	if not start:
		# Two Sundays ago
		start = datetime.datetime.now() + datetime.timedelta(days=6-datetime.datetime.now().weekday() - 21)
	else:
		start = datetime.datetime(*map(int, re.split('[^\d]', day)[:-1]))
	start = start.replace(hour=0, minute=0, second=0, microsecond=0)
	if not end:
		end = datetime.datetime.now() + datetime.timedelta(1)
	else:
		end = datetime.datetime(*map(int, re.split('[^\d]', day)[:-1]))
	end = end.replace(hour=0, minute=0, second=0, microsecond=0)

	VisitorCounter = vvmroster.VisitorCounter
	json_results = []
	results = VisitorCounter.query.filter(VisitorCounter.ts >= start,
										  VisitorCounter.ts < end)\
								   .order_by(VisitorCounter.ts)\
								   .all()
	items = vvmroster.accumulateVisitorsPerDay(results)
	print items

	workbook = xlsxwriter.Workbook(file)
	bold = workbook.add_format({'bold': 1})
	date_format = workbook.add_format({'num_format': 'd.m.yyyy'})
	worksheet = workbook.add_worksheet()
	worksheet.write_string(0, 0, 'Date', bold)
	worksheet.write_string(0, 1, 'Day', bold)
	worksheet.write_string(0, 2, '00-11', bold)
	worksheet.write_string(0, 3, '11-17', bold)
	worksheet.write_string(0, 4, '17-24', bold)

	row = 1
	for item in items:
		day = datetime.datetime(*map(int, re.split('[^\d]', item['ts'])[:-1]))
		print day
		worksheet.write_datetime(row, 0, day, date_format)
		worksheet.write_number  (row, 1, item['day'])
		worksheet.write_number  (row, 2, item['midnighttoeleven'])
		worksheet.write_number  (row, 3, item['eleventofive'])
		worksheet.write_number  (row, 4, item['fivetomidnight'])
		row = row + 1

	workbook.close()


@manager.command
def printLastestVisitorCount():
    results = vvmroster.VisitorCounter.query.order_by(vvmroster.VisitorCounter.ts.desc()).first()
    print results

if __name__ == "__main__":
    manager.run()

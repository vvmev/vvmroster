#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
import locale
locale.setlocale(locale.LC_ALL, 'de_DE')

from flask import Flask
from flask.ext.script import Manager
from flask.ext.mail import Mail, Message

prod = '/var/www/dienstplan.vvm.zs64.net/wsgi/vvmroster/production.cfg'
dev = os.getcwd() + '/dev.cfg'

os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = '/dev/null'
if os.path.exists(prod):
	os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = prod
elif os.path.exists(dev):
	os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = dev

import vvmroster

manager = Manager(vvmroster.app)
mail = Mail(vvmroster.app)


@manager.command
def sendNagMail():
	"Sends out an email if the minimum number of volunteers has not been met"
	day = vvmroster.thisSunday()
	dayFormatted = day.strftime('%A, %d. %B')
	counts = vvmroster.Roster.getCountsForSunday(day)
	if counts['open'] >= 2 and counts['close'] >= 2:
		return
	text = '''Liebe Kollegen,

am kommenden {day} fehlt in Aumühle noch Unterstützung! Damit wir
unseren Besuchern einen angenehmen Tag bereiten können, sollten mindestens zwei
von uns vor Ort sein. Die bisherigen Meldungen:
  Öffnen:    {counts[open]}
  Betreuen:  {counts[service]}
  Schließen: {counts[close]}

Bitte meldet euch unter http://dienstplan.vvm.zs64.net/ an!

Mit freundlichen Grüßen,
Der Dienstplaner
'''
	text = text.format(day=dayFormatted, counts=counts)
	#print text
	msg = Message(body=text,
		subject="Verstärkung am Sonntag benötigt!",
		sender="dienstplan@vvm.zs64.net", 
		recipients=vvmroster.app.config['NAG_EMAIL_RECIPIENTS'])
	mail.send(msg)


@manager.command
def initdb():
	"creates the database and fills it with some demo data"
	with vvmroster.app.app_context():
		vvmroster.initdb()


if __name__ == "__main__":
    manager.run()

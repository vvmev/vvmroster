#!/usr/bin/env python
# -*- coding: utf8 -*-

import os

prod = '/var/www/dienstplan.vvm.zs64.net/wsgi/vvmroster/production.cfg'

os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = '/dev/null'
if (os.path.exists(prod)):
	os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = prod

import vvmroster

with vvmroster.app.app_context():
	vvmroster.initdb()

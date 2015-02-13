#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
os.environ['VVMROSTER_APPLICATION_SETTINGS_PATH'] = '/var/www/dienstplan.vvm.zs64.net/wsgi/vvmroster/production.cfg'

import vvmroster

with vvmroster.app.app_context():
	vvmroster.initdb()

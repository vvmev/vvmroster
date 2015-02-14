#!/usr/bin/env python
# -*- coding: utf8 -*-

from ReverseProxied import ReverseProxied
import datetime
import re
import os
import time

import flask
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy.exc import DatabaseError, IntegrityError
from flask.ext.security import Security, SQLAlchemyUserDatastore, \
    UserMixin, RoleMixin, login_required, current_user
from flask.ext.security.utils import encrypt_password, verify_password
import sqlalchemy

# https://github.com/miguelgrinberg/Flask-Runner
# http://flask.pocoo.org/docs/0.10/deploying/mod_wsgi/

app = flask.Flask(__name__)
app.wsgi_app = ReverseProxied(app.wsgi_app)
db = SQLAlchemy(app)

app.config['LOCALE'] = 'de_DE'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///roster.db'
app.config['SECRET_KEY'] = 'developmentNotSoSecretKey'
app.config['SECURITY_PASSWORD_HASH'] = 'sha512_crypt'
app.config['SECURITY_PASSWORD_SALT'] = 'developmentNotSoSecretKey'
app.config['DEFAULT_MAIL_SENDER'] = 'VVM Dienstplan <vvm@zs64.net>'

if 'VVMROSTER_APPLICATION_SETTINGS_PATH' in os.environ:
	app.config.from_envvar('VVMROSTER_APPLICATION_SETTINGS_PATH')

# activate foreign key constraints on SQLite
@sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
	cursor = dbapi_connection.cursor()
	try:
		cursor.execute("PRAGMA foreign_keys=ON")
	except:
		pass
	cursor.close()

roles_users = db.Table('roles_users',
		db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
		db.Column('role_id', db.Integer(), db.ForeignKey('role.id')))

class Role(db.Model, RoleMixin):
	id = db.Column(db.Integer(), primary_key=True)
	name = db.Column(db.String(80), unique=True)
	description = db.Column(db.String(255))
	def __repr__(self):
		return '<Role {:d} {}>'.format(self.id, self.name)
	def __unicode__(self):
		return self.name

class User(db.Model, UserMixin):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(255))
	email = db.Column(db.String(255), unique=True)
	password = db.Column(db.String(255))
	active = db.Column(db.Boolean())
	confirmed_at = db.Column(db.DateTime())
	roles = db.relationship('Role', secondary=roles_users,
			backref=db.backref('users', lazy='dynamic'))
	def __repr__(self):
		return '<User {} {}>'.format(self.id, self.email)
	def __unicode__(self):
		return self.email

user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)


class Roster(db.Model):
	__tablename__ = 'roster'
	day = db.Column(db.DateTime, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
	user = db.relationship('User')
	will_open = db.Column(db.Boolean)
	will_service = db.Column(db.Boolean)
	will_close = db.Column(db.Boolean)
	comment = db.Column(db.String(1000))
	
	@classmethod
	def getCountsForSunday(self, day):
		counts = {
			'open': 0,
			'service': 0,
			'close': 0
		}
		for e in Roster.query.filter_by(day=day).all():
			if e.will_open:
				counts['open'] += 1
			if e.will_service:
				counts['service'] += 1
			if e.will_close:
				counts['close'] += 1
		return counts

	def __init__(self):
		self.day = datetime.date.today()
		self.will_open = False
		self.will_service = False
		self.will_close = False
		self.comment = ''

	def __repr__(self):
		return '<Roster {:d} {}>'.format(self.id, self.member_name)

@app.before_first_request
def initdb():
	db.create_all()
	admin_role = Role.query.filter_by(name='admin').first()
	if admin_role == None:
		admin_role = user_datastore.create_role(name='admin',
			description='manage users etc.')
	if user_datastore.get_user('stb@lassitu.de') == None:
		user_datastore.create_user(name='Stefan Bethke',
			email='stb@lassitu.de',
			password=encrypt_password('password'), roles=[admin_role])
	db.session.commit()


def thisSunday():
	today = datetime.datetime.combine(datetime.date.today(), datetime.datetime.min.time())
	# Sunday is the 6th day of the week
	return today + datetime.timedelta(days=6-today.weekday())



@app.route('/')
@login_required
def hello_world():
	return flask.render_template('index.html')


@app.route('/api/status')
@app.route('/api/status/1')
def status():
	if current_user.is_authenticated():
		sunday = thisSunday()
		r = dict()
		r['id'] = 1
		r['logged_in'] = True
		r['email'] = current_user.email
		r['name'] = current_user.name
		r['user_id'] = current_user.id
		r['admin_user'] = current_user.has_role('admin')
		r['today'] = sunday.isoformat()
		r['days'] = list((sunday + datetime.timedelta(days=i*7)).isoformat() for i in range(1,6))
		status=[]
		status.append(r)
		return flask.jsonify(items=status)
	return flask.jsonify(logged_in=False)


@app.route('/api/settings', methods=['POST', 'GET'])
@app.route('/api/settings/<id>', methods=['GET', 'PUT', 'POST'])
def settings(id=None):
	if not current_user.is_authenticated():
		flask.abort(403)
	user = current_user
	if flask.request.method == 'GET':
		json = [{
			'id': user.id,
			'name': user.name,
			'email': user.email,
			'passwprd': '',
			'roles': [unicode(role.name) for role in user.roles],
		}]
		return flask.jsonify(items=json)
	if flask.request.method == 'PUT':
		req = flask.request.get_json()
		print req
		current_user.email = req['email']
		current_user.name = req['name']
		db.session.commit()
		return flask.jsonify(ok=True)
	if flask.request.method == 'POST':
		req = flask.request.get_json()
		if not verify_password(req['old'], current_user.password):
			response = flask.jsonify(ok=False, msg='Das alte Passwort stimmt nicht.')
			response.status_code=409
			return response
		if req['new1'] != req['new2']:
			response = flask.jsonify(ok=False, msg='Die beiden neuen Passwörter stimmen nicht überein.')
			response.status_code=409
			return response
		current_user.password = encrypt_password(req['new1'])
		db.session.commit()
		return flask.jsonify(ok=True)
	flask.abort(405)


def dump(obj):
	for attr in dir(obj):
		print "obj.%s = %s" % (attr, getattr(obj, attr))

@app.route('/api/users', methods=['GET', 'POST'])
@app.route('/api/users/<id>', methods=['GET', 'PUT', 'DELETE'])
def users(id=None):
	if not current_user.is_authenticated():
		flask.abort(403)
	if not current_user.has_role('admin'):
		flask.abort(403)

	admin_role = Role.query.filter_by(name='admin').first()
	if id:
		user = User.query.filter_by(id=id).first()
	if flask.request.method == 'GET':
		json = []
		for user in User.query.all():
			u = {
				'id': user.id,
				'name': user.name,
				'email': user.email,
				'passwprd': '',
				'roles': [unicode(role.name) for role in user.roles],
				'admin_user': admin_role in user.roles,
			}
			json.append(u)
		return flask.jsonify(items=json)
	if flask.request.method == 'DELETE' and id:
		try:
			db.session.delete(user)
			db.session.commit()
		except DatabaseError as e:
			response = flask.jsonify(ok=False, msg='Benutzer kann nicht gelöscht werden: ' + e.message)
			response.status_code=409
			return response
		return flask.jsonify(ok=True)
	if flask.request.method == 'PUT':
		roles = []
		req = flask.request.get_json()
		if 'admin_user' in req:
			roles.append(admin_role)
		try:
			user.name = req['name']
			user.email = req['email']
			if 'password' in req:
				user.password = encrypt_password(req['password'])
			user.roles = roles
			db.session.commit()
		except IntegrityError:
			response = flask.jsonify(ok=False, msg='Es gibt bereits einen Benutzer mit dieser Email (doppelter Datensatz)')
			response.status_code=409
			return response
		except DatabaseError as e:
			response = flask.jsonify(ok=False, msg='beim Speichern des Benutzers: ' + e.message)
			response.status_code=409
			return response
		return flask.jsonify(ok=True, id=user.id)
	if flask.request.method == 'POST':
		roles = []
		req = flask.request.get_json()
		if 'admin_user' in req and req['admin_user']:
			roles.append(admin_role)
		try:
			user = user_datastore.create_user(name=req['name'],
				email=req['email'],
				password=encrypt_password(req['password']),
				roles=roles)
			db.session.commit()
		except IntegrityError:
			response = flask.jsonify(ok=False, msg='Es gibt bereits einen Benutzer mit dieser Email (doppelter Datensatz)')
			response.status_code=409
			return response
		except DatabaseError as e:
			response = flask.jsonify(ok=False, msg='beim Speichern des Benutzers: ' + e.message)
			response.status_code=409
			return response
		return flask.jsonify(ok=True, id=user.id)
	flask.abort(405)


@app.route('/api/roster/<day>', methods=['GET', 'POST'])
@app.route('/api/roster/<day>/<int:id>', methods=['PUT'])
def rosterentries(day, id=None):
	if not current_user.is_authenticated():
		flask.abort(403)
	if not day:
		print "foo"
		response = flask.jsonify(ok=False, msg='')
		response.status_code = 404
		return response
	day = datetime.datetime(*map(int, re.split('[^\d]', day)[:-1]))
	if flask.request.method == 'GET':
		results = Roster.query.filter_by(day=day).all()
		json_results = []
		for result in results:
			d = {
				'day': result.day.isoformat(),
				'member': result.user.name,
				'user_id': result.user.id,
				'id': result.user.id,
				'will_open': result.will_open,
				'will_service': result.will_service,
				'will_close': result.will_close,
				'comment': result.comment
				}
			json_results.append(d)
		return flask.jsonify(items=json_results)
	if flask.request.method == 'POST':
		req = flask.request.get_json()
		if req['user_id'] != current_user.id and not current_user.has_role('admin'):
			flask.abort(403)
		r = Roster()
		r.day = day;
		r.user = User.query.get(req['user_id'])
		r.will_open =    req['will_open']
		r.will_service = req['will_service']
		r.will_close =   req['will_close']
		r.comment = req['comment']
		db.session.add(r)
		db.session.commit()
		return flask.jsonify(ok=True)
	if flask.request.method == 'PUT':
		req = flask.request.get_json()
		if id != current_user.id and not current_user.has_role('admin'):
			flask.abort(403)
		r = Roster.query.filter_by(day=day, user_id=id).first()
		r.will_open =    req['will_open']
		r.will_service = req['will_service']
		r.will_close =   req['will_close']
		r.comment = req['comment']
		print "committing"
		db.session.commit()
		return flask.jsonify(ok=True)
	flask.abort(405)

    
if __name__ == '__main__':
	app.run(port=5001, debug=True)

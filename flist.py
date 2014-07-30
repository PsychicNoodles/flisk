from flask import Flask, render_template, url_for, session, request, flash, redirect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, ForeignKey, desc, distinct
from sqlalchemy.types import DateTime, Integer, String, Boolean
from sqlalchemy.sql.expression import func
from sqlalchemy.orm import sessionmaker
from binascii import hexlify
import os
import time
import sys

Base = declarative_base()
class Gist(Base):
	__tablename__ = "gists"
	__table_args__ = {"sqlite_autoincrement" : True}

	id = Column(Integer, primary_key = True)
	title = Column(String, nullable = False)
	author = Column(String)
	public = Column(Boolean, nullable = False, default = lambda: True)

	def __repr__(self):
		return "<Gist(id = '%s', title = '%s', author = '%s', public = '%s')>" % (self.id, self.title, self.author, self.public)

class File(Base):
	__tablename__ = "files"
	__table_args__ = {"sqlite_autoincrement" : True}

	id = Column(Integer, primary_key = True)
	gist = Column(Integer, ForeignKey("gists.id"), nullable = False)
	path = Column(String, nullable = False)
	checksum = Column(String, nullable = False, unique = True)
	added = Column(DateTime, default = func.now(), nullable = False)

	def __repr__(self):
		return "<File(id = '%s', gist = '%s', path = '%s', checksum = '%s', added = '%s')>" % (self.id, self.gist, self.path, self.checksum, self.added)

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
SqlSession = sessionmaker()
SqlSession.configure(bind = engine)

#s = SqlSession()
#return s.query(Gist, File).filter(Gist.id == File.gist).order_by(Gist.id).order_by(desc(File.added)).order_by(File.added).limit(limit).all()

def create_gist(title, author, path, checksum, public = True):
	s = SqlSession()
	g = Gist(title = title, author = author, public = public)
	s.add(g)
	s.flush()
	f = File(gist = s.id, path = path, checksum = checksum)
	s.add(f)
	s.commit()

def add_file(gist, path, checksum):
	s = SqlSession()
	s.add(File(gist = gist, path = path, checksum = checksum))
	s.commit()

def slurp(path):
	with open(path) as f:
		return f.read()

def get_recent_gists(limit = 10):
	#s = SqlSession()
	#return s.query(Gist, File).filter(Gist.id == File.gist).order_by(Gist.id).order_by(desc(File.added)).order_by(File.added).limit(limit).all()
	s = SqlSession()
	ret = s.query(Gist, File).filter(Gist.id == File.gist).filter(Gist.public == True).order_by(desc(Gist.id))
	return map(lambda x: list(x).append(slurp(x[1].path)), list(ret))

def get_gist(gid):
	s = SqlSession()
	return s.query(Gist, File).filter(Gist.id == File.gist).filter(Gist.id == gid).first()


class TimedSet(set): # http://stackoverflow.com/a/16137224
	#this solution for managing session ids only works on single-threaded servers like the flask dev server
	def __init__(self):
		self._table_ = {}

	def add(self, item, timeout = 0):
		self._table_[item] = time.time() + timeout

	def __contains__(self, item):
		if item in self._table_.keys():
			if self._table_[item] > time.time():
				return True
			else:
				del self._table_[item]
		return False

app = Flask(__name__)
app.debug = True
app.secret_key = "supersecret"
uber_password = sys.argv[1] if len(sys.argv) != 1 else "thisisapassword"
session_timeout = 60 * 60 * 12 # 12 hours

def is_valid(key):
	global valid_sessions
	return key in valid_sessions

def add_session(key, ti):
	global valid_sessions
	valid_sessions.add(key, ti)

def valid_passwd(pw):
	global uber_password
	return uber_password == pw

def get_session_timeout():
	global session_timeout
	return session_timeout

valid_sessions = TimedSet()

@app.before_request
def session_check():
	if not request.path.startswith("/static"):
		sess = session.get("session_id")
		if sess is not None:
			if is_valid(sess):
				app.logger.debug("Request from %s with valid session id %s" % (request.remote_addr, sess))
				return
			else:
				app.logger.debug("Request from %s with INVALID session id %s" % (request.remote_addr, sess))
				session.pop("session_id")
				flash(sess, "sess_err")
				if request.path != "/auth":
					return redirect("/auth")
		if request.path == "/auth":
			passwd = request.form.get("passwd")
			if passwd is not None:
				if valid_passwd(passwd):
					sess = hexlify(os.urandom(6))
					app.logger.debug("Request from %s with valid password, adding session id %s" % (request.remote_addr, sess))
					session["session_id"] = sess
					add_session(sess, get_session_timeout())
				else:
					app.logger.debug("Request from %s with INVALID password (%s)" % (request.remote_addr, passwd))
					flash(passwd, "attempt")

@app.route("/auth", methods = ["GET", "POST"])
def auth():
	return render_template("auth.html")

@app.route("/")
def index():
	return render_template("listing.html", listings = get_recent_gists())

if app.debug:
	@app.route("/session")
	def sess_test():
		return "%s - %s" % (session.get("session_id"), is_valid(session.get("session_id")))

	@app.route("/gimme")
	def give_sess():
		sess = hexlify(os.urandom(6))
		session["session_id"] = sess
		add_session(sess, get_session_timeout())
		return "done"

	@app.route("/getgist")
	def getgist():
		return get_gist(1)

	@app.route("/addgist")
	def add():
		create_gist("eltit", "rohtua", "/a/", "checkem")
		return "okay"

if __name__ == "__main__":
	print "Starting server with password %s and session timeout %s seconds." % (uber_password, session_timeout)
	app.run()
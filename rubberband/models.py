import random, string

from bs4 import BeautifulSoup
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Boolean, Date, DocType, Index, Integer, Object, Search, String
from elasticsearch_dsl.query import SimpleQueryString
from flask.ext.login import UserMixin
from flask.ext.sqlalchemy import SQLAlchemy
from markdown import markdown
from oauth2client.client import OAuth2Credentials
from sqlalchemy.dialects.postgresql import JSONB

from rubberband import app

db = SQLAlchemy(app)
es_client = Elasticsearch()
es = Search(using=es_client)

class Domain(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	url = db.Column(db.Text, nullable=False, index=True)
	primary = db.Column(db.Boolean, default=False, index=True)
	verified = db.Column(db.Boolean)

	site_id = db.Column(db.Integer, db.ForeignKey('site.id'))

	@property
	def owner(self):
	    return self.site.owner

	def __init__(self, url, site, primary=False, verified=False):
		self.url = url
		self.primary = primary
		self.verified = verified
		self.site = site

class Site(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	slug = db.Column(db.Text, index=True, nullable=False, unique=True)
	secret = db.Column(db.Text, index=True, nullable=False, unique=True)
	public = db.Column(db.Boolean, default=True)

	owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)

	domains = db.relationship('Domain', backref='site', lazy='dynamic', foreign_keys='Domain.site_id')

	def __init__(self, slug, owner, secret=None):
		self.slug = slug
		self.owner = owner
		if not secret:
			self.generate_secret()

	def generate_secret(self):
		self.secret = ''.join(random.choice(string.ascii_lowercase + \
			string.ascii_uppercase + string.digits) for i in range(24))


class User(db.Model, UserMixin):
	id = db.Column(db.Integer, primary_key=True)
	picture = db.Column(db.Text)
	display_name = db.Column(db.Text)
	email = db.Column(db.Text, index=True, unique=True)
	credentials_json = db.Column(JSONB)

	sites = db.relationship('Site', backref='owner', lazy='dynamic')

	@property
	def credentials(self):
		if self.credentials_json:
			return OAuth2Credentials.from_json(self.credentials_json)
		else:
			return None

	def is_authenticated(self):
		return True

	def is_active(self):
		return True

	def is_anonymous(self):
		return False

	def get_id(self):
		return self.id


class Page(DocType):
	"""Each site lives in its own index."""
	created = Date()
	path = String()
	site_id = Integer()
	fields = Object()
	body = String()

	@property
	def site(self):
		return Site.query.get(self.site_id)

	@property
	def primary_domain(self):
		return Domain.query.filter_by(site=self.site, primary=True).one()


	def set_html(self, body):
		soup = BeautifulSoup(body, 'html.parser')
		self.body = soup.get_text()

	def set_markdown(self, body):
		self.set_html(markdown(body))

	class Meta:
		using = es_client


# class Event(DocType):
# 	"""
# 	category: add, remove, search, visit
# 	data: added or removed url, search id
# 	"""
# 	created = Date()
# 	category = String(index='not_analyzed')
# 	user = Integer()

# 	class Meta:
# 		using = es_client


# class Visit(Event):
#	"""Click redirect plus view"""
# 	search_id = String(index='not_analyzed')
# 	document_id = String(index='not_analyzed')


# class Search(Event):
#   """Search event"""
# 	autocomplete = Boolean()
# 	query = Object()  # Support faceted search later
# 	results = String(multi=True)


# class Subscription(db.Model):
# 	"""Subscribe to tag or category updates"""
# 	id = db.Column(db.Integer, primary_key=True)

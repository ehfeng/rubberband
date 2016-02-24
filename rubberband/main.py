from datetime import datetime
import hashlib
import html
import httplib2
import json
from urllib.parse import urlparse

from flask import abort, Flask, redirect, render_template, request, Response, url_for
from flask.ext.login import current_user, LoginManager, login_required, login_user, logout_user
from flask.ext.cors import cross_origin
from flask_wtf import Form
import googleapiclient
from oauth2client.client import HttpAccessTokenRefreshError, OAuth2WebServerFlow
import requests
from sqlalchemy.orm.exc import NoResultFound

from rubberband import app, config
from rubberband.forms import DomainForm, SiteForm
from rubberband.models import db, Domain, User, Page, Site

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

if 'sentry' in config:
	sentry = Sentry(
		app,
		dsn=config['sentry']['DSN'],
	)
else:
	app.debug = True

@app.route('/')
def home():
	return render_template('home.html')

################
# Site Console #
################

@app.route('/account')
@login_required
def account():
	return render_template('account.html')


@app.route('/site/new', methods=['GET', 'POST'])
@login_required
def create_site():
	form = SiteForm()
	if form.validate_on_submit():
		site = Site(slug=form.slug.data, owner=current_user)
		domain = Domain(url=form.url.data, primary=True, site=site)
		db.session.add(site, domain)
		db.session.commit()
		Page.init(index=site.slug)
		return redirect(url_for('account'))

	return render_template('create_site.html', form=form)


@app.route('/site/<slug>/domain/add', methods=['GET', 'POST'])
@login_required
def add_domain(slug):
	site = Site.query.filter_by(slug=slug).one()
	form = DomainForm()
	if form.validate_on_submit():
		domain = Domain(url=form.url.data, site=site)
		if not site.domains:
			domain.primary = True
		db.session.add(domain)
		db.session.commit()
		return redirect(url_for('site', slug=site.slug))

	return render_template('add_domain.html', site=site, form=form)


@app.route('/domain/<domain_id>/delete', methods=['POST'])
@login_required
def remove_domain(domain_id):
	domain = Domain.query.get(domain_id)
	slug = domain.site.slug
	if current_user == domain.owner:
		db.session.delete(domain)
		db.session.commit()

	return redirect(url_for('site', slug=slug))


@app.route('/add', methods=['POST'])
def add():
	"""
	Index new content

	POST args:
		secret (str): site secret
		path (str): path of the content
		title (str): document title
		format (str): body's content format. plaintext, markdown, html
		hash (str): hash of body
		modified (Optional[datetime])
		... (add custom attributes)
	Request body:
		Content to be indexed
	"""
	missing_args = [key for key in ['secret', 'path', 'format'] if key not in request.args.keys()]
	if missing_args:
		abort(400)

	fmt = request.args.get('format').lower()
	if fmt not in ['plaintext', 'txt', 'markdown', 'md', 'html', 'htm']:
		abort(400)

	site = Site.query.filter_by(secret=request.args.get('secret')).first()
	if not site:
		abort(400)

	if request.args.get('modified'):
		try:
			modified = datetime.strptime(request.args.get('modified'), '%Y-%m-%d %H:%M:%S %Z%z')
		except ValueError:
			modified = datetime.now()
	else:
		modified = datetime.now()

	m = hashlib.md5()
	m.update(request.data)
	if request.args.get('hash') != m.hexdigest():
		abort(400)

	if Page.get(index=site.slug, id=m.hexdigest(), ignore=404):
		return ('', 200)

	p = Page()
	p.path = request.args.get('path')
	p.created = modified
	p.meta.id = request.args.get('hash')
	p.site_id = site.id

	extras = [ key for key in request.args.keys() if key not in ['secret', 'url', 'format', 'modified'] ]
	for key in extras:
		p[key] = request.args.get(key)

	if fmt in ['plaintext', 'txt']:
		p.body = request.data

	elif fmt in ['markdown', 'md']:
		p.set_markdown(request.data.decode('utf-8'))

	elif fmt in ['html', 'htm']:
		p.set_html(request.data)

	p.save(index=site.slug)
	return ('', 200)


@app.route('/remove', methods=['POST'])
def remove():
	"""
	Unindex content

	POST args:
		secret (str)
		path (Optional[str]): Delete specific URL. If blank, delete all URLs from ES
	"""
	site = Site.query.filter_by(secret=request.args.get('secret')).first()
	if not site:
		abort(400)

	path = request.args.get('path')
	if path:
		# TODO implement later
		pass
	else:
		search = Page.search()
		search.doc_type = Page
		[ d.delete(index=site.slug) for d in search.execute() ]
		return ('', 200)

##########
# Search #
##########

@app.route('/<slug>', methods=['GET', 'POST'])
def site(slug):
	"""
	GET args:
		q (Optional[str]): Query string
		sort (Optional[str]): datetime, matches
		order (Optional[str]): asc or desc
		... (custom attribute search)
	"""
	q = request.args.get('q')
	if q:
		from elasticsearch_dsl.query import SimpleQueryString
		pages = Page.search().query(SimpleQueryString(query=q)).execute()
		return render_template('search.html', pages=pages)
	else:
		pages = Page.search().execute()
		return render_template('site.html', pages=pages)

	pages_dict = [ {'path': p.to_dict()['path'], 'body': p.to_dict()['body']} for p in pages]
	referer = urlparse(request.headers.get('Referer'))
	if referer.netloc == config['rubberband']['host']:
		return render_template('search.html', pages=pages_dict)



@app.route('/search')
@cross_origin(methods=['GET'])
def search():
	"""
	site based on ORIGIN and REFERER request header
	Also, rubberband.io/<slug>

	Confirm domain based on /search (for example, rubberband.io/search), which should include
	the app_id in a meta tag. This page also makes XHR GET requests for results
	Of course, CORS in dev will just be http://localhost:4000

	POST for autocomplete
	GET or POST args:
		q (Optional[str]): Query string
		sort (Optional[str]): datetime, matches
		order (Optional[str]): asc or desc
		... (custom attribute search)
	GET or POST return:
		JSON { results: [ { title, url, redirect, snippet }, ... ], count }
	"""
	referer = urlparse(request.headers.get('Referer'))
	if request.headers.get('Origin'):
		# CORS AJAX request
		pass
	elif current_user.is_authenticated and referer.netloc == config['rubberband']['host']:
		# Internal request
		slug = referer.path[1:].lower()  # TODO do a better job checking this
		try:
			site = Site.query.filter_by(slug=slug).one()
			query = request.args.get('q')
			return json.dumps([(d['url'], d['body']) for d in Page.simple_search(query)])
		except NoResultFound:
			abort(404)
	else:
		# TODO general search
		return render_template('search.html')
	return ''


########
# User #
########

def get_flow():
	flow = OAuth2WebServerFlow(
		client_id=config['google']['client_id'],
		client_secret=config['google']['client_secret'],
		scope='https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile',
		redirect_uri=config['google']['redirect_uri'],
		)
	flow.params['access_type'] = 'offline'
	flow.params['prompt'] = 'consent'
	return flow

@login_manager.user_loader
def load_user(user_id):
	user = User.query.get(user_id)
	if user and user.credentials and (user.credentials.refresh_token is None
		or user.credentials.access_token_expired):
		try:
			user.credentials.refresh(httplib2.Http())
			db.session.add(user)
			db.session.commit()
			return user
		except HttpAccessTokenRefreshError:
			user.credentials = None
			db.session.add(user)
			db.session.commit()
			return None
	return user


@app.route('/login')
def login():
	"""
	GET args:
		next (url): redirect or use Referer header

	Get name, gender, profile picture, and email address
	"""
	if current_user.is_authenticated and current_user.credentials and (current_user.credentials.refresh_token or
		request.args.get('force') != 'True'):
		return redirect(next_url or url_for('home'))

	flow = get_flow()
	next_url = request.args.get('next') or request.headers.get('Referer')
	flow.params['state'] = next_url
	return redirect(flow.step1_get_authorize_url())

@app.route('/oauth_finish')
def oauth_finish():
	credentials = get_flow().step2_exchange(request.args.get('code'))
	response = requests.get('https://www.googleapis.com/oauth2/v1/userinfo?alt=json',
		headers={'Authorization': 'Bearer ' + credentials.access_token}).json()
	user = User.query.filter_by(email=response['email']).first()
	if not user:
		user = User()
		user.email = response['email']
		user.display_name = response['name']
		user.picture = response['picture']
		user.credentials_json = credentials.to_json()
		db.session.add(user)
		db.session.commit()

	login_user(user, remember=True)
	return redirect(request.args.get('state') or url_for('account'))

@app.route('/logout')
def logout():
	"""
	GET args:
		redirect (url): redirect or use Referer header
	"""
	logout_user()
	return redirect(request.args.get('next') or request.headers.get('Referer') or url_for('index'))

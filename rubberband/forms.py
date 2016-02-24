from flask_wtf import Form
from wtforms import StringField
from wtforms.fields.html5 import URLField
from wtforms.validators import DataRequired, url


class SiteForm(Form):
    slug = StringField('short name', validators=[DataRequired()])
    url = URLField('primary domain url', validators=[url()])


class DomainForm(Form):
	url = URLField('domain url', validators=[url()])

from os import path
from jinja2 import Environment, FileSystemLoader


email_template = Environment(loader=FileSystemLoader(
    path.dirname(path.abspath(__file__))
)).get_template('email_template.jinja2')


class HTMLEmail():

    def __init__(self, govuk_banner=True):
        self.govuk_banner = govuk_banner

    def __call__(self, body):
        return email_template.render({
            'body': body,
            'govuk_banner': self.govuk_banner
        })

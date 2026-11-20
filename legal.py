"""Public policy pages: Terms, Privacy, Refunds, Contact (English + Urdu).

Business details come from the environment (vault), never from the code:
BUSINESS_NAME, BUSINESS_OWNER, BUSINESS_ADDRESS, CONTACT_EMAIL, CONTACT_PHONE,
CONTACT_HOURS. Empty values are simply not shown; admins see what is missing.
"""
import logging
import os
from datetime import date

from flask import render_template

log = logging.getLogger('rakhza')

# Bump when the wording of any policy changes.
UPDATED = date(2026, 11, 16)
UPDATED_LABEL = {'en': '16 November 2026', 'ur': '16 نومبر 2026'}

PAGES = {
    # endpoint: (url, English title, Urdu title)
    'terms': ('/terms', 'Terms of Service', 'شرائط و ضوابط'),
    'privacy': ('/privacy', 'Privacy Policy', 'رازداری کی پالیسی'),
    'refunds': ('/refund-policy', 'Refund and Cancellation Policy', 'رقم کی واپسی اور منسوخی کی پالیسی'),
    'contact': ('/contact', 'Contact us', 'ہم سے رابطہ'),
}
FIELDS = ('BUSINESS_NAME', 'BUSINESS_OWNER', 'BUSINESS_ADDRESS', 'CONTACT_EMAIL', 'CONTACT_PHONE', 'CONTACT_HOURS')
REQUIRED = ('BUSINESS_OWNER', 'BUSINESS_ADDRESS', 'CONTACT_EMAIL', 'CONTACT_PHONE')


def register_legal(app):
    for key in FIELDS:
        app.config.setdefault(key, os.getenv(key, '').strip())
    if not app.config['BUSINESS_NAME']:
        app.config['BUSINESS_NAME'] = 'Rakhza'
    if not app.config['CONTACT_HOURS']:
        app.config['CONTACT_HOURS'] = 'Mon–Sat, 10:00–18:00 PKT'

    def biz():
        c = app.config
        return dict(
            name=c['BUSINESS_NAME'], owner=c['BUSINESS_OWNER'], address=c['BUSINESS_ADDRESS'],
            email=c['CONTACT_EMAIL'], phone=c['CONTACT_PHONE'], hours=c['CONTACT_HOURS'],
            missing=[k for k in REQUIRED if not c[k]],
        )

    def make_view(endpoint, en_title, ur_title):
        def view():
            from flask import g
            lang = getattr(g, 'lang', 'en')
            return render_template(
                f'legal/{endpoint}.html', heading=ur_title if lang == 'ur' else en_title,
                page=endpoint, biz=biz(), updated=UPDATED_LABEL.get(lang, UPDATED_LABEL['en']),
            )
        view.__name__ = endpoint
        return view

    for endpoint, (url, en_title, ur_title) in PAGES.items():
        app.add_url_rule(url, endpoint, make_view(endpoint, en_title, ur_title), methods=['GET'])

    @app.context_processor
    def legal_links():
        return dict(legal_pages=PAGES)

    missing = biz()['missing']
    if missing and not app.config.get('TESTING'):
        log.warning('policy pages: business details not set: %s', ','.join(missing))

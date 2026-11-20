"""Public policy pages JazzCash reviews: Terms, Privacy, Refunds, Contact."""
from pathlib import Path

import pytest

from test_signup import app, client, signup, token  # noqa: F401  (fixtures)
from test_trial import step

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    '/terms': ('Terms of Service', 'شرائط و ضوابط'),
    '/privacy': ('Privacy Policy', 'رازداری کی پالیسی'),
    '/refund-policy': ('Refund and Cancellation Policy', 'رقم کی واپسی اور منسوخی کی پالیسی'),
    '/contact': ('Contact us', 'ہم سے رابطہ'),
}
DETAILS = dict(BUSINESS_NAME='Rakhza Test Traders', BUSINESS_OWNER='Test Owner',
               BUSINESS_ADDRESS='Shop 1, Test Market, Lahore', CONTACT_EMAIL='help@example.invalid',
               CONTACT_PHONE='03000000000')


@pytest.mark.parametrize('url', PAGES)
def test_pages_are_public_bilingual_and_indexable(client, url):
    en, ur = PAGES[url]
    r = client.get(url)
    assert r.status_code == 200
    assert f'<h1 class="hero-title">{en}</h1>' in r.text
    assert 'index,follow' in r.text and 'Last updated' in r.text
    switched = client.get(f'/language/ur?page={url.strip("/").replace("refund-policy", "refunds")}')
    assert switched.location.endswith(url)
    page = client.get(url).text
    assert f'<h1 class="hero-title">{ur}</h1>' in page and 'dir="rtl"' in page


def test_footer_links_everywhere(client):
    for path in ('/', '/login', '/terms'):
        html = client.get(path).text
        for url in PAGES:
            assert f'href="{url}"' in html
    assert 'noindex,nofollow' in client.get('/login').text


def test_signup_links_terms_and_drops_poc_warning(client):
    html = client.get('/').text
    assert 'By creating an account you agree to our <a href="/terms">Terms of Service</a>' in html
    assert 'fictional' not in html
    assert 'fictional' not in client.get('/login').text


def test_business_details_shown_when_set(client, app):
    app.config.update(DETAILS)
    for url in PAGES:
        html = client.get(url).text
        assert 'Rakhza Test Traders' in html
        assert 'help@example.invalid' in html and 'tel:03000000000' in html
        assert 'Shop 1, Test Market, Lahore' in html


def test_missing_details_hidden_from_public_flagged_for_admin(client, app):
    html = client.get('/contact').text
    assert 'mailto:' not in html and 'tel:' not in html
    assert 'Office only' not in html
    app.config.update(ADMIN_PHONES='03001234567')
    signup(client)
    assert 'Office only' in client.get('/contact').text
    assert 'CONTACT_EMAIL' in client.get('/contact').text


def test_expired_shop_can_still_read_policies(client, app):
    app.config.update(TESTER_PHONES='03001234567')
    signup(client)
    for _ in range(6):
        step(client)
    assert client.get('/dashboard').status_code == 302  # locked out of the app...
    for url in PAGES:
        assert client.get(url).status_code == 200  # ...but not out of the policies


def test_policies_match_the_product():
    terms = (ROOT / 'templates' / 'legal' / 'terms.html').read_text(encoding='utf-8')
    refunds = (ROOT / 'templates' / 'legal' / 'refunds.html').read_text(encoding='utf-8')
    privacy = (ROOT / 'templates' / 'legal' / 'privacy.html').read_text(encoding='utf-8')
    assert 'Rs 299' in terms and '5 days' in terms and 'no automatic charges' in terms.lower()
    assert 'no automatic charges' in refunds.lower() and '7 working days' in refunds
    assert 'hash' in privacy and 'JazzCash' in privacy
    vault = (ROOT / 'secrets' / 'rakhza.env.example').read_text(encoding='utf-8')
    for key in ('BUSINESS_OWNER', 'BUSINESS_ADDRESS', 'CONTACT_EMAIL', 'CONTACT_PHONE'):
        assert key + '=' in vault

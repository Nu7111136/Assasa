from pathlib import Path
import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable
from main import User, Payment, ReconNote, database_uri

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('prefix', ['postgres://', 'postgresql://', 'postgresql+psycopg://'])
def test_neon_database_url_preserves_credentials_and_ssl(prefix):
    suffix = 'tester:p%40ss@db.example.invalid/neondb?sslmode=require&channel_binding=require'
    assert database_uri(prefix + suffix) == 'postgresql+psycopg://' + suffix


@pytest.mark.parametrize('value', [None, '', '   '])
def test_empty_database_url_falls_back_to_sqlite(value):
    assert database_uri(value) == 'sqlite:///asasa.db'


def test_sqlite_url_unchanged():
    assert database_uri('sqlite:///test.db') == 'sqlite:///test.db'


def test_postgresql_schema_compiles_and_migration_preserves_timezone():
    dialect = postgresql.dialect()
    for model in (User, Payment, ReconNote):
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect))
        assert 'CREATE TABLE' in ddl and 'TIMESTAMP WITH TIME ZONE' in ddl
    assert User.__table__.c.paid_until.type.compile(dialect=dialect) == 'TIMESTAMP WITH TIME ZONE'
    assert User.__table__.c.paid_until.type.compile(dialect=sqlite.dialect()) == 'DATETIME'
    user_ddl = str(CreateTable(User.__table__).compile(dialect=dialect))
    assert 'billing_day' in user_ddl


def test_blueprint_and_wsgi():
    yaml = (ROOT/'render.yaml').read_text(encoding='utf-8')
    for text in ('plan: free', 'runtime: python', 'pip install -r requirements.txt',
                 'flask --app main upgrade-db && gunicorn wsgi:app',
                 'generateValue: true', 'sync: false', 'value: production',
                 'key: COOKIE_SECURE', 'key: PAYMENT_JAZZCASH_NUMBER', 'key: LOG_LEVEL', '--bind 0.0.0.0:$PORT'):
        assert text in yaml
    assert '03036666758' not in yaml
    requirements = (ROOT/'requirements.txt').read_text(encoding='utf-8')
    assert 'gunicorn' in requirements and 'psycopg[binary]' in requirements
    from wsgi import app
    assert app.test_client().get('/login').status_code == 200


def test_upgrade_db_new_sqlite_is_idempotent(app):
    runner=app.test_cli_runner()
    assert runner.invoke(args=['upgrade-db']).exit_code == 0
    assert runner.invoke(args=['upgrade-db']).exit_code == 0


def test_tester_guide_contains_real_urdu_not_encoding_placeholders():
    guide=(ROOT/'TESTERS.md').read_text(encoding='utf-8')
    assert sum(0x600 <= ord(c) <= 0x6ff for c in guide) > 900
    assert '????' not in guide

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from vault import _split_envs, MAGIC  # noqa: E402


def test_split_envs_shared_and_named_blocks():
    text = """
CADDY_EMAIL=ops@rakhza.digital
POSTGRES_PASSWORD=pg
# ===== STAGING =====
APP_ENV=staging
SECRET_KEY=stage
# ===== PRODUCTION =====
APP_ENV=production
SECRET_KEY=live
"""
    parts = _split_envs(text)
    assert 'CADDY_EMAIL=ops@rakhza.digital' in parts['staging']
    assert 'CADDY_EMAIL=ops@rakhza.digital' in parts['production']
    assert 'APP_ENV=staging' in parts['staging']
    assert 'APP_ENV=production' in parts['production']
    assert 'SECRET_KEY=live' not in parts['staging']
    assert 'SECRET_KEY=stage' not in parts['production']


def test_lock_unlock_roundtrip(tmp_path, monkeypatch):
    import vault
    monkeypatch.setattr(vault, 'SECRETS', tmp_path)
    monkeypatch.setattr(vault, 'PLAIN', tmp_path / 'rakhza.env')
    monkeypatch.setattr(vault, 'VAULT', tmp_path / 'rakhza.vault')
    monkeypatch.setattr(vault, 'STAGING_OUT', tmp_path / '.env.staging')
    monkeypatch.setattr(vault, 'PROD_OUT', tmp_path / '.env.prod')
    vault.PLAIN.write_text(
        'POSTGRES_PASSWORD=pg\n# ===== STAGING =====\nAPP_ENV=staging\n'
        '# ===== PRODUCTION =====\nAPP_ENV=production\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('RAKHZA_VAULT_PASSWORD', 'test-vault-pass-not-real')
    vault.cmd_lock()
    assert vault.VAULT.exists()
    raw = vault.VAULT.read_bytes()
    assert raw.startswith(MAGIC)
    vault.PLAIN.unlink()
    vault.cmd_unlock()
    staging = vault.STAGING_OUT.read_text(encoding='utf-8')
    prod = vault.PROD_OUT.read_text(encoding='utf-8')
    assert 'APP_ENV=staging' in staging
    assert 'APP_ENV=production' in prod
    assert 'POSTGRES_PASSWORD=pg' in staging and 'POSTGRES_PASSWORD=pg' in prod

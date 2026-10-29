"""Local-only credentials and one-attempt UI login. Never print credential values."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

BASE = 'https://learn.onbriton.com'


@dataclass(frozen=True)
class Credentials:
    email: str = field(repr=False)
    password: str = field(repr=False)


def default_credentials_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BritonHelper' / 'credentials.json'


def load_credentials(filename=None, environ=None):
    env = os.environ if environ is None else environ
    email, password = env.get('BRITON_EMAIL'), env.get('BRITON_PASSWORD')
    if email is not None or password is not None:
        if not email or not password:
            raise ValueError('BRITON_EMAIL dan BRITON_PASSWORD harus diisi berpasangan')
    else:
        configured = filename or env.get('BRITON_CREDENTIALS_FILE')
        path = Path(configured).expanduser() if configured else default_credentials_path()
        if not path.exists():
            if configured:
                raise ValueError('File kredensial yang diminta tidak ditemukan')
            return None
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict) or set(data) != {'email','password'}:
                raise ValueError()
            email, password = data['email'], data['password']
        except Exception:
            raise ValueError('Format kredensial harus JSON dengan email dan password saja') from None
    if not isinstance(email,str) or not isinstance(password,str) or not email.strip() or not password:
        raise ValueError('Email/password lokal tidak valid')
    if email != email.strip() or '@' not in email or email in ('YOUR_EMAIL','ISI_EMAIL_ANDA') or password in ('YOUR_PASSWORD','ISI_PASSWORD_ANDA'):
        raise ValueError('Isi kredensial lokal dengan akunmu; jangan gunakan placeholder contoh')
    return Credentials(email=email, password=password)


def trusted_origin(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and parsed.netloc == 'learn.onbriton.com'


async def login_wall(page):
    return urlparse(page.url).path.rstrip('/') == '/login' or await page.locator('input[type=password]').count() > 0


async def ensure_signed_in(page, credentials_file=None):
    if not trusted_origin(page.url):
        raise RuntimeError('Login dibatalkan: halaman bukan HTTPS learn.onbriton.com')
    if not await login_wall(page):
        return False
    creds = load_credentials(credentials_file)
    if creds is None:
        raise RuntimeError('Belum login. Isi file kredensial lokal/variabel lingkungan, atau jalankan login manual.')
    try:
        email = page.locator('form input#email[name=email][type=email]')
        password = page.locator('form input#password[name=password][type=password]')
        button = page.locator('form button#btnSignIn[type=submit]')
        if await email.count()!=1 or await password.count()!=1 or await button.count()!=1:
            raise RuntimeError('Struktur login berubah')
        # Refuse to send credentials if a form action points to a different origin.
        action = await email.locator('xpath=ancestor::form').get_attribute('action')
        from urllib.parse import urljoin
        if not trusted_origin(urljoin(page.url, action or page.url)):
            raise RuntimeError('Tujuan login tidak tepercaya')
        await email.fill(creds.email)
        await password.fill(creds.password)
        if not trusted_origin(page.url):
            raise RuntimeError('Halaman login berubah')
        await button.click()  # Exactly one attempt, no retry loop.
        await page.wait_for_url(lambda url: trusted_origin(str(url)) and urlparse(str(url)).path.rstrip('/') != '/login', timeout=30000)
        if not trusted_origin(page.url) or await login_wall(page):
            raise RuntimeError('Login belum terverifikasi')
        await page.locator('body').wait_for(state='visible')
    except Exception:
        # Playwright call logs may include fill values: never re-raise their raw exception.
        raise RuntimeError('Login otomatis belum berhasil diverifikasi. Periksa akun atau langkah verifikasi di situs; tidak dicoba ulang otomatis.') from None
    finally:
        # Do not erase browser form fields via scripts; just release the local reference.
        creds = None
    return True

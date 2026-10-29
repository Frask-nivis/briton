import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from login_helper import Credentials, load_credentials, trusted_origin, ensure_signed_in


class CredentialTests(unittest.TestCase):
    def test_env_pair(self):
        creds=load_credentials(environ={'BRITON_EMAIL':'test@example.invalid','BRITON_PASSWORD':'test-only-value'})
        self.assertEqual(creds.email,'test@example.invalid')
        self.assertNotIn('test-only-value',repr(creds))
        self.assertNotIn('test@example.invalid',repr(creds))

    def test_partial_env_rejected(self):
        with self.assertRaises(ValueError): load_credentials(environ={'BRITON_EMAIL':'test@example.invalid'})

    def test_empty_env_rejected(self):
        with self.assertRaises(ValueError): load_credentials(environ={'BRITON_EMAIL':'','BRITON_PASSWORD':''})

    def test_file_bom(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'credentials.json'
            path.write_text(json.dumps({'email':'test@example.invalid','password':'test-only-value'}),encoding='utf-8-sig')
            self.assertEqual(load_credentials(path,environ={}).email,'test@example.invalid')

    def test_env_precedence(self):
        creds=load_credentials('does-not-exist.json',environ={'BRITON_EMAIL':'test@example.invalid','BRITON_PASSWORD':'test-only-value'})
        self.assertEqual(creds.email,'test@example.invalid')

    def test_explicit_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): load_credentials(Path(d)/'missing.json',environ={})

    def test_default_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d, patch('login_helper.default_credentials_path',return_value=Path(d)/'missing.json'):
            self.assertIsNone(load_credentials(environ={}))

    def test_example_placeholder_rejected(self):
        with self.assertRaises(ValueError): load_credentials(environ={'BRITON_EMAIL':'ISI_EMAIL_ANDA','BRITON_PASSWORD':'ISI_PASSWORD_ANDA'})

    def test_bad_json_sanitized(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'credentials.json'; path.write_text('bad test-only-value')
            with self.assertRaises(ValueError) as caught: load_credentials(path,environ={})
            self.assertNotIn('test-only-value',str(caught.exception))

    def test_unexpected_fields_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'credentials.json'; path.write_text(json.dumps({'email':'a@b.invalid','password':'value','extra':'x'}))
            with self.assertRaises(ValueError): load_credentials(path,environ={})

    def test_origin_restrictions(self):
        for url in ('http://learn.onbriton.com/login','https://learn.onbriton.com.evil.invalid/login','https://evil.invalid/login','https://learn.onbriton.com@evil.invalid/login'):
            self.assertFalse(trusted_origin(url))
        self.assertTrue(trusted_origin('https://learn.onbriton.com/login'))


class Locator:
    def __init__(self,page,kind): self.page=page; self.kind=kind
    async def count(self):
        if self.kind=='input[type=password]': return int('/login' in self.page.url)
        return 1
    def locator(self,selector): return Locator(self.page,'form')
    async def get_attribute(self,name): return self.page.action
    async def fill(self,value): self.page.filled.append(self.kind)
    async def click(self):
        self.page.clicks+=1
        if self.page.fail: raise RuntimeError('fill value test-only-value must not leak')
        self.page.url='https://learn.onbriton.com/dashboard'
    async def wait_for(self,**kwargs): pass


class Page:
    def __init__(self,url='https://learn.onbriton.com/login',action=None,fail=False):
        self.url=url; self.action=action; self.fail=fail; self.clicks=0; self.filled=[]
    def locator(self,selector): return Locator(self,selector)
    async def wait_for_url(self,predicate,**kwargs):
        if not predicate(self.url): raise TimeoutError('not signed in')


class LoginTests(unittest.IsolatedAsyncioTestCase):
    def creds(self): return patch('login_helper.load_credentials',return_value=Credentials('test@example.invalid','test-only-value'))

    async def test_auto_login_one_click(self):
        page=Page()
        with self.creds(): self.assertTrue(await ensure_signed_in(page))
        self.assertEqual(page.clicks,1)
        self.assertEqual(len(page.filled),2)

    async def test_existing_session_no_credentials_read(self):
        page=Page('https://learn.onbriton.com/dashboard')
        with patch('login_helper.load_credentials',side_effect=AssertionError('must not read')):
            self.assertFalse(await ensure_signed_in(page))
        self.assertEqual(page.clicks,0)

    async def test_wrong_origin_no_fill(self):
        page=Page('https://evil.invalid/login')
        with self.creds(),self.assertRaises(RuntimeError): await ensure_signed_in(page)
        self.assertFalse(page.filled)

    async def test_external_form_action_no_fill(self):
        page=Page(action='https://evil.invalid/collect')
        with self.creds(),self.assertRaises(RuntimeError): await ensure_signed_in(page)
        self.assertFalse(page.filled)
        self.assertEqual(page.clicks,0)

    async def test_failure_sanitized_no_retry(self):
        page=Page(fail=True)
        with self.creds(),self.assertRaises(RuntimeError) as caught: await ensure_signed_in(page)
        self.assertNotIn('test-only-value',str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(page.clicks,1)

    async def test_no_credentials_no_fill(self):
        page=Page()
        with patch('login_helper.load_credentials',return_value=None),self.assertRaises(RuntimeError):
            await ensure_signed_in(page)
        self.assertFalse(page.filled)


if __name__=='__main__': unittest.main()

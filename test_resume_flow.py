"""Mocked workflow tests; these do not launch Playwright or submit to Brit On."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Allow import-only workflow tests in a runtime without Playwright installed.
if importlib.util.find_spec('playwright') is None:
    package=types.ModuleType('playwright'); api=types.ModuleType('playwright.async_api')
    api.async_playwright=lambda: None; api.expect=lambda x: None
    with patch.dict(sys.modules, {'playwright':package,'playwright.async_api':api}):
        import briton
else:
    import briton


class Form:
    def __init__(self,text=''): self.text=text; self.click=AsyncMock(side_effect=self.grade)
    async def grade(self): self.text='Your answer: Correct'
    async def evaluate(self,script):
        return {'controls':[dict(tag='INPUT',type='text',visible=True,disabled=False,value='answer')], 'total_slots':0,'empty_slots':0}
    async def inner_text(self): return self.text
    def locator(self,selector): return self


class Page:
    def __init__(self,text=''):
        self.form=Form(text); self.screenshot=AsyncMock(); self.url='https://learn.onbriton.com/course/learn/1?group=1'
    def locator(self,selector): return self.form


class ResumeFlowTests(unittest.IsolatedAsyncioTestCase):
    async def run_plan(self,page,directory,submit=True,answer='KIRIM',status_only=False):
        plan={'reviewed':True,'activities':[{'url':page.url,'retry':False,'actions':[{'type':'fill','form':'#miniQuizForm1','selector':'input','value':'answer'}]}]}
        path=Path(directory)/'plan.json'; path.write_text(json.dumps(plan))
        async def identity(x): return x
        with patch.object(briton,'ROOT',Path(directory)), patch.object(briton,'navigate',AsyncMock()), patch.object(briton,'unique',identity), patch.object(briton,'inspect_all',AsyncMock(return_value=['same'])), patch.object(briton,'inspect_action',AsyncMock(return_value='same')), patch.object(briton,'validate_complete',AsyncMock()), patch.object(briton,'apply_action',AsyncMock()) as write, patch.object(briton,'wait_for_feedback',AsyncMock(return_value={'feedback':[]})), patch('builtins.input',return_value=answer):
            await briton.apply_plan(page,str(path),submit,False,status_only=status_only)
            return write

    async def test_graded_skipped_without_click_or_fill(self):
        with tempfile.TemporaryDirectory() as d:
            page=Page('Your answer: Correct'); write=await self.run_plan(page,d)
            page.form.click.assert_not_awaited(); write.assert_not_awaited()
            self.assertEqual(json.loads((Path(d)/'plan.checkpoint.json').read_text())['activities'][page.url]['status'],'graded')

    async def test_cancel_preserves_unsubmitted(self):
        with tempfile.TemporaryDirectory() as d:
            page=Page(); await self.run_plan(page,d,answer='BATAL')
            page.form.click.assert_not_awaited()
            self.assertEqual(json.loads((Path(d)/'plan.checkpoint.json').read_text())['activities'][page.url]['status'],'filled_unsubmitted')

    async def test_dry_run_no_submit(self):
        with tempfile.TemporaryDirectory() as d:
            page=Page(); await self.run_plan(page,d,submit=False)
            page.form.click.assert_not_awaited()

    async def test_confirmed_submit_saved_graded(self):
        with tempfile.TemporaryDirectory() as d:
            page=Page(); await self.run_plan(page,d)
            page.form.click.assert_awaited_once()
            self.assertEqual(json.loads((Path(d)/'plan.checkpoint.json').read_text())['activities'][page.url]['status'],'graded')

    async def test_failed_click_persists_unknown_blocks_next_run(self):
        with tempfile.TemporaryDirectory() as d:
            page=Page(); page.form.click.side_effect=TimeoutError('network')
            with self.assertRaises(RuntimeError): await self.run_plan(page,d)
            self.assertEqual(json.loads((Path(d)/'plan.checkpoint.json').read_text())['activities'][page.url]['status'],'submission_unknown')
            page.form.click.reset_mock()
            with self.assertRaises(RuntimeError): await self.run_plan(page,d)
            page.form.click.assert_not_awaited()

    async def test_status_only_no_fill_submit(self):
        with tempfile.TemporaryDirectory() as d:
            page=Page(); write=await self.run_plan(page,d,submit=False,status_only=True)
            page.form.click.assert_not_awaited(); write.assert_not_awaited()


if __name__=='__main__': unittest.main()

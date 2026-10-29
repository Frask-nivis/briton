import json
import tempfile
import unittest
from pathlib import Path
from progress import Checkpoint, classify, should_block_resume
from existing_answers import inspect_action, inspect_all


def snapshot(**kw):
    return dict(controls=[], total_slots=5, empty_slots=5, **kw)


class ProgressTests(unittest.TestCase):
    def test_retry_not_graded(self):
        self.assertEqual(classify(snapshot(),'Retry activity'),'unanswered')

    def test_feedback_graded(self):
        self.assertEqual(classify(snapshot(),'Your answer: Correct'),'graded')

    def test_multiline_incorrect_graded(self):
        self.assertEqual(classify(snapshot(),'Your answer:\nIncorrect, it should be X'),'graded')

    def test_dropdown_feedback_graded(self):
        self.assertEqual(classify(snapshot(),'Your answer: has seen, Correct: has seen'),'graded')

    def test_partial_feedback_uncertain(self):
        self.assertEqual(classify(snapshot(can_submit=True),'Your answer: Correct'),'uncertain')

    def test_unknown_feedback_uncertain(self):
        self.assertEqual(classify(snapshot(),'Your answer: pending'),'uncertain')

    def test_empty_unknown_form_unsupported(self):
        self.assertEqual(classify({'controls':[]},''),'unsupported')

    def test_filled_drop(self):
        self.assertEqual(classify({'controls':[], 'total_slots':5,'empty_slots':4},''),'filled_unsubmitted')

    def test_filled_control(self):
        for c in [dict(tag='INPUT',type='radio',checked=True),dict(tag='INPUT',type='text',value='x'),dict(tag='SELECT',type='select-one',selected=[dict(placeholder=False,value='x')])]:
            c.update(visible=True,disabled=False)
            self.assertEqual(classify({'controls':[c]},''),'filled_unsubmitted')

    def test_uncertain_submit_blocks_resume(self):
        for prev in ('submission_pending','submission_unknown'):
            for live in ('unanswered','filled_unsubmitted','uncertain'):
                self.assertTrue(should_block_resume(prev,live))
            self.assertFalse(should_block_resume(prev,'graded'))

    def test_checkpoint_roundtrip_no_answers(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json'; plan={'reviewed':True,'activities':[]}
            cp=Checkpoint(path,plan); cp.record('https://learn.onbriton.com/course/learn/149?group=753','blocked','conflict')
            self.assertEqual(Checkpoint(path,plan).state('https://learn.onbriton.com/course/learn/149?group=753'),'blocked')
            self.assertFalse(path.with_name(path.name+'.tmp').exists())
            self.assertNotIn('actions',json.loads(path.read_text()))

    def test_wrong_plan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json'; cp=Checkpoint(path,{'reviewed':True}); cp.record('url','graded','feedback')
            with self.assertRaises(ValueError): Checkpoint(path,{'reviewed':False})


class FakeControl:
    def __init__(self, value='', checked=False, kind='text', other_checked=False, selected=None):
        self.value=value; self.checked=checked; self.kind=kind; self.other_checked=other_checked
        self.selected=selected or []; self.name='q1'
    async def count(self): return 1
    async def wait_for(self,**kwargs): pass
    async def is_disabled(self): return False
    async def input_value(self): return self.value
    async def is_checked(self): return self.checked
    async def get_attribute(self,name): return {'type':self.kind,'name':self.name}.get(name)
    async def evaluate(self,script): return self.selected
    def locator(self,selector): return self
    async def evaluate_all(self,script,*args):
        return self.other_checked if args else ['answer']


class FakeForm:
    def __init__(self,controls): self.controls=controls
    async def count(self): return 1
    async def wait_for(self,**kwargs): pass
    async def get_attribute(self,name): return 'miniQuizForm1' if name=='id' else None
    def locator(self,selector):
        if selector=='input[type=radio]:checked': return self.controls['answer']
        return self.controls[selector]


class FakePage:
    def __init__(self,controls): self.form=FakeForm(controls)
    def locator(self,selector): return self.form


class ExistingAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_fill(self):
        page=FakePage({'answer':FakeControl()})
        self.assertEqual(await inspect_action(page,{'type':'fill','form':'#miniQuizForm1','selector':'answer','value':'new'},'miniQuizForm1'),'empty')

    async def test_same_fill(self):
        page=FakePage({'answer':FakeControl(value='new')})
        self.assertEqual(await inspect_action(page,{'type':'fill','form':'#miniQuizForm1','selector':'answer','value':'new'},'miniQuizForm1'),'same')

    async def test_different_fill_blocked(self):
        for old in ('old',' '):
            control=FakeControl(value=old); page=FakePage({'answer':control})
            with self.assertRaises(RuntimeError):
                await inspect_action(page,{'type':'fill','form':'#miniQuizForm1','selector':'answer','value':'new'},'miniQuizForm1')
            self.assertEqual(control.value,old)

    async def test_radio_conflict(self):
        c=FakeControl(kind='radio',other_checked=True)
        with self.assertRaises(RuntimeError):
            await inspect_action(FakePage({'answer':c}),{'type':'check','form':'#miniQuizForm1','selector':'answer'},'miniQuizForm1')

    async def test_same_radio(self):
        c=FakeControl(kind='radio',checked=True)
        self.assertEqual(await inspect_action(FakePage({'answer':c}),{'type':'check','form':'#miniQuizForm1','selector':'answer'},'miniQuizForm1'),'same')

    async def test_dropdown_conflict(self):
        c=FakeControl(selected=[dict(text='old',value='old',disabled=False,hidden=False)])
        with self.assertRaises(RuntimeError):
            await inspect_action(FakePage({'answer':c}),{'type':'select','form':'#miniQuizForm1','selector':'answer','label':'answer'},'miniQuizForm1')

    async def test_same_dropdown(self):
        c=FakeControl(selected=[dict(text='answer',value='x',disabled=False,hidden=False)])
        self.assertEqual(await inspect_action(FakePage({'answer':c}),{'type':'select','form':'#miniQuizForm1','selector':'answer','label':'answer'},'miniQuizForm1'),'same')

    async def test_full_preflight_conflict_no_writes(self):
        empty=FakeControl(); old=FakeControl(value='old')
        page=FakePage({'a':empty,'b':old})
        actions=[dict(type='fill',form='#miniQuizForm1',selector=s,value='new') for s in ('a','b')]
        with self.assertRaises(RuntimeError): await inspect_all(page,actions,'miniQuizForm1')
        self.assertEqual(empty.value,'')
        self.assertEqual(old.value,'old')

    async def test_cross_form_blocked(self):
        with self.assertRaises(ValueError):
            await inspect_action(FakePage({'answer':FakeControl()}),dict(type='fill',form='#miniQuizForm1',selector='answer',value='new'),'miniQuizForm2')


if __name__=='__main__': unittest.main()

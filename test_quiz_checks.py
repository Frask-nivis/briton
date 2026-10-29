import asyncio
import unittest
from quiz_checks import completeness_errors, format_issues, parse_feedback, validate_complete, wait_for_feedback


def control(kind, **extra):
    return dict(tag='INPUT', type=kind, visible=True, disabled=False, name='q1', value='', checked=False, **extra)


class ChecksTest(unittest.TestCase):
    def test_radio_empty(self):
        self.assertTrue(completeness_errors({'controls':[control('radio')]}))

    def test_radio_checked(self):
        c=control('radio'); c['checked']=True
        self.assertFalse(completeness_errors({'controls':[c]}))

    def test_each_radio_group(self):
        a=control('radio'); a['checked']=True
        b=control('radio'); b['name']='q2'
        self.assertIn('q2', completeness_errors({'controls':[a,b]})[0])

    def test_disabled_radio_ignored(self):
        c=control('radio'); c['disabled']=True
        self.assertFalse(completeness_errors({'controls':[c]}))

    def test_hidden_ignored(self):
        c=control('text'); c['visible']=False
        self.assertFalse(completeness_errors({'controls':[c]}))

    def test_dropdown_placeholder(self):
        c=control('select-one'); c.update(tag='SELECT',selected=[{'value':'0','placeholder':True}])
        self.assertTrue(completeness_errors({'controls':[c]}))

    def test_dropdown_answer(self):
        c=control('select-one'); c.update(tag='SELECT',selected=[{'value':'answer','placeholder':False}])
        self.assertFalse(completeness_errors({'controls':[c]}))

    def test_empty_text_and_drop(self):
        self.assertEqual(len(completeness_errors({'controls':[control('text')],'empty_slots':1})),2)

    def test_preserve_punctuation(self):
        value='Have you ever tried sushi?'
        self.assertTrue(format_issues(value))
        self.assertEqual(value,'Have you ever tried sushi?')
        format_issues(value,{'terminal_punctuation':'?'})

    def test_explicit_no_period(self):
        with self.assertRaises(ValueError):
            format_issues('Anna packed her suitcase last night.',{'terminal_punctuation':'none'})

    def test_exact_literal(self):
        with self.assertRaises(ValueError):
            format_issues("I'm planning to",{'expected_literal':'I’m planning to'})

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError):
            format_issues('answer',{'strip_punctuation':True})

    def test_feedback(self):
        r=parse_feedback('Your answer: Correct\nYour answer: Incorrect, it should be X')
        self.assertEqual(r['correct_explicit'],1)
        self.assertEqual(r['incorrect_explicit'],1)

    def test_multiline_feedback(self):
        r=parse_feedback('Your answer:\n\nIncorrect, it should be\nX')
        self.assertEqual(r['incorrect_explicit'],1)
        self.assertIn('\nX',r['raw_text'])

    def test_exact_text_is_not_score(self):
        r=parse_feedback('Your answer: hello., Correct: hello\nYour answer: yes, Correct: yes')
        self.assertEqual([x['status'] for x in r['feedback']],['different_text','exact_match'])
        self.assertEqual(r['correct_explicit'],0)

    def test_unknown_not_success(self):
        self.assertEqual(parse_feedback('Your answer:')['feedback'][0]['status'],'unknown')

    def test_validate_async_blocks(self):
        class Form:
            async def evaluate(self, script): return {'controls':[control('radio')]}
        with self.assertRaises(RuntimeError): asyncio.run(validate_complete(Form()))

    def test_timeout_propagates_without_click(self):
        class Page:
            async def wait_for_function(self,*args,**kwargs): raise TimeoutError('network')
        with self.assertRaises(TimeoutError): asyncio.run(wait_for_feedback(Page(),'miniQuizForm1'))


if __name__=='__main__':
    unittest.main()

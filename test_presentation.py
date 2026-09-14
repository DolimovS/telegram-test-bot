import unittest
from presentation import render, preview, chunks, NAV
from bot import Bot

class PresentationTests(unittest.TestCase):
    def row(self):
        return dict(code='12345678',uid=2,submitted=0,answers='BA',score=1,wrong='[2]')
    def test_question_marks_and_summary(self):
        text=render(self.row())
        for expected in ['1. B ✅','2. A ❌','1 / 2','50.0%','To‘g‘ri: 1','Xato: 1']:
            self.assertIn(expected,text)
        self.assertNotIn('2. B',text)
        self.assertNotIn('2. C',text)
        self.assertNotIn('2. D',text)
    def test_delayed_never_marks_or_scores(self):
        r=self.row(); r['score']=None; r['wrong']=None
        text=render(r)
        for forbidden in ['✅','❌','50.0%','Ball:','To‘g‘ri:','Xato:']:
            self.assertNotIn(forbidden,text)
        self.assertIn('2. A',text)
    def test_preview_no_correctness(self):
        text=preview('123','BA')
        self.assertIn('1. B',text)
        for forbidden in ['✅','❌','Ball:','%']: self.assertNotIn(forbidden,text)
    def test_long_result_complete_utf16_safe(self):
        r=self.row(); r.update(answers='A'*2000,score=1999,wrong='[2000]')
        text=render(r); parts=list(chunks(text))
        self.assertGreater(len(parts),1)
        self.assertEqual(''.join(parts),text)
        self.assertIn('2000. A ❌',parts[-1])
        self.assertTrue(all(len(p.encode('utf-16-le'))//2<=3500 for p in parts))
        self.assertEqual(''.join(chunks('🎓'*5000)), '🎓'*5000)
    def test_buttons_only_on_final_chunk(self):
        class Fake(Bot):
            def api(self,method,**data): sent.append(data)
        from unittest.mock import patch
        sent=[]
        with patch('bot.time.sleep'):
            Fake('',None).send(2,'🎓'*4000,NAV)
        self.assertGreater(len(sent),1)
        self.assertNotIn('reply_markup',sent[0])
        self.assertEqual(sent[-1]['reply_markup']['inline_keyboard'],NAV)

if __name__=='__main__': unittest.main()

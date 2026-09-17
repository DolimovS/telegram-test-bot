import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from core import Store
from bot import Bot

class FakeBot(Bot):
    def __init__(self,store): super().__init__('',store); self.sent=[]; self.calls=[]
    def send(self,uid,text,buttons=None): self.sent.append((uid,text,buttons))
    def api(self,method,**data): self.calls.append(method); return True

class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name+'/db',1);self.bot=FakeBot(self.s)
    def tearDown(self): self.tmp.cleanup()
    def callback(self,uid,action):
        self.bot.handle({'callback_query':{'id':'test','from':{'id':uid},'message':{'chat':{'type':'private','id':uid}},'data':action}})
    def test_start_button_and_history_reply_keyboard(self):
        for text in ['/start','▶️ Boshlash']:
            self.bot.handle({'message':{'from':{'id':2},'chat':{'type':'private','id':2},'text':text}})
            keyboard=self.bot.sent[-2][2]
            self.assertTrue(keyboard['is_persistent'])
            self.assertEqual(keyboard['keyboard'][0][0]['text'],'▶️ Boshlash')
            self.assertNotIn('new',str(self.bot.sent[-1]))
        self.bot.handle({'message':{'from':{'id':2},'chat':{'type':'private','id':2},'text':'📚 Mening tarixim'}})
        self.assertIn('Tarix',self.bot.sent[-1][1]);self.assertEqual(self.bot.calls,[])
    def test_archive_closes_blocks_and_retains_history(self):
        code=self.s.create(1,'AB',True)
        p,*_=self.s.preview(2,code+' AC');self.s.confirm(2,p)
        pending,*_=self.s.preview(3,code+' AB')
        self.s.archive(1,code)
        with self.assertRaises(ValueError):self.s.preview(3,code+' AB')
        with self.assertRaises(ValueError):self.s.confirm(3,pending)
        self.assertEqual(self.s.history(2)[0]['score'],1)
        self.assertEqual(self.s.manage_tests(1)[3],0)
        self.assertEqual(self.s.manage_tests(1,True)[3],1)
        self.s.unarchive(1,code)
        self.assertTrue(self.s.test_details(1,code)['closed'])
        self.assertEqual(self.s.manage_tests(1)[3],1)
    def test_all_management_operations_require_admin(self):
        code=self.s.create(1,'A',False)
        for call in [lambda:self.s.archive(2,code),lambda:self.s.unarchive(2,code),lambda:self.s.delete_empty(2,code),lambda:self.s.test_details(2,code),lambda:self.s.manage_tests(2)]:
            with self.assertRaises(ValueError):call()
        for action in ['tests','tests:archive:0','test:'+code,'archive:'+code,'unarchive:'+code,'delete:'+code,'delete_yes:'+code]:
            self.callback(2,action);self.assertIn('administrator',self.bot.sent[-1][1])
        self.assertFalse(self.s.test_details(1,code)['archived'])
    def test_empty_delete_requires_ui_confirmation_and_invalidates_pending(self):
        code=self.s.create(1,'A',False);p,*_=self.s.preview(2,code+' A')
        self.callback(1,'delete:'+code)
        self.assertIn('delete_yes:'+code,str(self.bot.sent[-1][2]))
        self.assertIsNotNone(self.s.test_details(1,code))
        self.callback(1,'delete_yes:'+code)
        with self.assertRaises(ValueError):self.s.test_details(1,code)
        with self.assertRaises(ValueError):self.s.confirm(2,p)
        with self.s.db() as c:self.assertIsNotNone(c.execute('SELECT code FROM retired_codes WHERE code=?',(code,)).fetchone())
    def test_cannot_delete_submitted_test_and_offers_archive(self):
        code=self.s.create(1,'A',False);p,*_=self.s.preview(2,code+' A');self.s.confirm(2,p)
        for action in ['delete:'+code,'delete_yes:'+code]:
            self.callback(1,action);self.assertIn('archive:'+code,str(self.bot.sent[-1][2]))
        self.assertEqual(len(self.s.history(2)),1)
    def test_delete_vs_confirm_race_never_orphans_attempt(self):
        for i in range(10):
            code=self.s.create(1,'A',False);p,*_=self.s.preview(2,code+' A')
            def run(fn):
                try:fn()
                except ValueError:pass
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(run,[lambda:self.s.delete_empty(1,code),lambda:self.s.confirm(2,p)]))
            with self.s.db() as c:
                orphan=c.execute('SELECT a.code FROM attempts a LEFT JOIN tests t USING(code) WHERE t.code IS NULL').fetchone()
                self.assertIsNone(orphan)
    def test_pagination_separates_archives_and_has_actions(self):
        codes=[self.s.create(1,'A',False) for _ in range(12)]
        self.s.archive(1,codes[0])
        seen=[]
        for page in range(3):
            rows,actual,pages,total=self.s.manage_tests(1,page=page)
            seen.extend(r['code'] for r in rows)
            self.assertEqual((pages,total),(3,11));self.assertEqual(actual,page)
        self.assertEqual(len(set(seen)),11);self.assertNotIn(codes[0],seen)
        self.callback(1,'tests');self.assertIn('tests:active:1',str(self.bot.sent[-1][2]))
        self.callback(1,'test:'+codes[1]);self.assertIn('archive:'+codes[1],str(self.bot.sent[-1][2]))
    def test_existing_schema_upgrades_without_losing_rows(self):
        import sqlite3
        path=self.tmp.name+'/legacy'
        with sqlite3.connect(path) as c:
            c.executescript("CREATE TABLE tests(code TEXT PRIMARY KEY,key TEXT,delayed INTEGER,deadline REAL,closed INTEGER); INSERT INTO tests VALUES('12345678','A',0,NULL,0);")
        c.close()
        upgraded=Store(path,1)
        self.assertEqual(upgraded.test_details(1,'12345678')['archived'],0)

if __name__=='__main__':unittest.main()

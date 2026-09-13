import tempfile, unittest, time
from concurrent.futures import ThreadPoolExecutor
from core import Store, answers
from bot import Bot

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.s=Store(self.tmp.name+'/db',1)
    def tearDown(self): self.tmp.cleanup()
    def test_parser(self):
        self.assertEqual(answers('acbd'),'ACBD')
        self.assertEqual(answers('2-b, 1-a 3:C'),'ABC')
        for value in ['1-A 1-B','1-A 3-B','ABCE','0-A','1-A,2-E','']:
            with self.assertRaises(ValueError): answers(value)
    def test_admin(self):
        for action in [lambda:self.s.create(2,'A',0),lambda:self.s.close(2,'123'),lambda:self.s.tests(2),lambda:self.s.history(2,True)]:
            with self.assertRaises(ValueError): action()
    def test_private_and_spoofed_callbacks(self):
        class Fake(Bot):
            def api(self,*args,**kwargs): return True
            def send(self,*args,**kwargs): pass
        b=Fake('',self.s)
        b.handle({'message':{'chat':{'id':-1,'type':'group'},'from':{'id':1},'text':'AB | -'}})
        b.handle({'callback_query':{'id':'x','from':{'id':2},'message':{'chat':{'id':2,'type':'private'}},'data':'mode:1'}})
        with self.s.db() as c: self.assertIsNone(c.execute("SELECT * FROM settings WHERE key='draft'").fetchone())
    def test_visibility_and_isolation(self):
        code=self.s.create(1,'AB',True)
        token,_,_=self.s.preview(2,code+' AC'); self.s.confirm(2,token)
        self.assertIsNone(self.s.history(2)[0]['score'])
        self.assertIsNone(self.s.history(2)[0]['wrong'])
        self.assertEqual(self.s.history(3),[])
        self.assertEqual(self.s.history(1,True)[0]['score'],1)
        self.s.close(1,code)
        self.assertEqual(self.s.history(2)[0]['wrong'],'[2]')
    def test_immediate_and_unique(self):
        a=self.s.create(1,'AB',False); b=self.s.create(1,'BA',False)
        self.assertNotEqual(a,b)
        token,_,_=self.s.preview(2,a+' AB'); self.s.confirm(2,token)
        self.assertEqual(self.s.history(2)[0]['score'],2)
    def test_atomic_attempt(self):
        code=self.s.create(1,'AB',False)
        tokens=[self.s.preview(2,code+' AB')[0] for _ in range(8)]
        def submit(token):
            try: self.s.confirm(2,token); return 1
            except ValueError: return 0
        with ThreadPoolExecutor(max_workers=8) as pool: self.assertEqual(sum(pool.map(submit,tokens)),1)
        self.assertEqual(len(self.s.history(2)),1)
        with self.assertRaises(ValueError): self.s.preview(2,code+' AB')
    def test_deadline_and_confirmation_owner(self):
        code=self.s.create(1,'AB',True,time.time()+60)
        token,_,_=self.s.preview(2,code+' AB')
        with self.assertRaises(ValueError): self.s.confirm(3,token)
        with self.assertRaises(ValueError): self.s.preview(2,code+' A')
        with self.s.db() as c: c.execute('UPDATE tests SET deadline=? WHERE code=?',(time.time()-1,code))
        with self.assertRaises(ValueError): self.s.confirm(2,token)
        self.s.expire(); self.assertTrue(self.s.tests(1)[0]['closed'])
    def test_manual_close_recheck_and_persistence(self):
        code=self.s.create(1,'A',True,time.time()+60)
        token,_,_=self.s.preview(2,code+' A'); self.s.close(1,code)
        with self.assertRaises(ValueError): self.s.confirm(2,token)
        self.assertTrue(Store(self.s.path,1).tests(1)[0]['closed'])

if __name__=='__main__': unittest.main()

import tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from core import Store

class CodeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.s=Store(self.temp.name+'/db',1)
    def tearDown(self): self.temp.cleanup()
    def test_numeric_length_and_concurrent_unique(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            codes=list(pool.map(lambda _:self.s.create(1,'A',0),range(24)))
        self.assertEqual(len(set(codes)),24)
        for code in codes: self.assertRegex(code,r'^[1-9][0-9]{3}$')
    def test_collision_excluded_closed_code_preserved(self):
        with self.s.db() as c:
            c.execute("INSERT INTO tests(code,key,delayed,closed) VALUES('1000','A',0,1)")
        with patch('core.secrets.choice',side_effect=lambda available:available[0]):
            self.assertEqual(self.s.create(1,'B',0),'1001')
            self.assertEqual(self.s.create(1,'C',0),'1002')
    def test_exhaustion(self):
        with self.s.db() as c:
            c.executemany('INSERT INTO tests(code,key,delayed) VALUES(?,?,?)',((str(i),'A',0) for i in range(1000,10000)))
        with self.assertRaisesRegex(ValueError,'Barcha 4 xonali'):
            self.s.create(1,'B',0)
        self.assertEqual(len(self.s.tests(1)),9000)
    def test_old_code_still_works(self):
        with self.s.db() as c:
            c.execute("INSERT INTO tests(code,key,delayed) VALUES('12345678','A',0)")
        new=self.s.create(1,'B',0)
        self.assertEqual(len(new),4)
        token,code,_=self.s.preview(2,'12345678 A')
        self.s.confirm(2,token)
        self.assertEqual(self.s.history(2)[0]['code'],'12345678')
        self.assertEqual(code,'12345678')

if __name__=='__main__': unittest.main()

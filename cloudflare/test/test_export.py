import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('exporter', Path(__file__).resolve().parents[1] / 'scripts/export_legacy.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ExportTest(unittest.TestCase):
    def test_preserves_old_codes_scores_and_quotes_without_exporting_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'old.sqlite3'
            destination = Path(directory) / 'dump.sql'
            with sqlite3.connect(source) as c:
                c.executescript('CREATE TABLE tests(code,key,delayed,deadline,closed,archived); CREATE TABLE attempts(code,uid,answers,submitted,score,wrong,notified); CREATE TABLE settings(key,value); CREATE TABLE retired_codes(code);')
                c.execute('INSERT INTO tests VALUES(?,?,?,?,?,?)', ('12345678', 'AB', 1, None, 1, 1))
                c.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?)', ('12345678', 2, 'AC', 12345, 1, '[2]', 1))
                c.execute('INSERT INTO settings VALUES(?,?)', ('secret', "do-not-export'"))
                c.execute("INSERT INTO retired_codes VALUES('1000')")
            c.close()
            counts = module.export(source, destination)
            self.assertEqual(counts, {'tests': 1, 'attempts': 1})
            self.assertNotIn('do-not-export', destination.read_text())
            with sqlite3.connect(':memory:') as imported:
                imported.executescript((Path(__file__).resolve().parents[1] / 'migrations/0001_initial.sql').read_text())
                imported.executescript(destination.read_text())
                self.assertEqual(imported.execute('SELECT code,score,answers FROM attempts').fetchone(), ('12345678', 1, 'AC'))
                self.assertEqual(imported.execute('SELECT archived FROM tests').fetchone(), (1,))
                self.assertEqual(imported.execute('SELECT code FROM retired_codes').fetchone(), ('1000',))
            with self.assertRaises(ValueError): module.export(source, destination)

if __name__ == '__main__': unittest.main()

import re, secrets, sqlite3, time, json
from contextlib import contextmanager

def answers(text):
    text = text.strip().upper()
    if re.fullmatch(r'[ABCD]+', text):
        return text
    parts = re.split(r'[,;\s]+', text)
    found = {}
    for part in parts:
        m = re.fullmatch(r'([1-9]\d*)[-.:]([ABCD])', part)
        if not m or int(m[1]) in found:
            raise ValueError('Javoblar formati xato yoki raqam takrorlangan.')
        found[int(m[1])] = m[2]
    if set(found) != set(range(1, len(found)+1)):
        raise ValueError('Savol raqamlari ketma-ket va to‘liq bo‘lishi kerak.')
    return ''.join(found[i] for i in range(1, len(found)+1))

class Store:
    def __init__(self, path, admin):
        self.path, self.admin = path, admin
        with self.db() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tests(code TEXT PRIMARY KEY, key TEXT NOT NULL, delayed INTEGER NOT NULL, deadline REAL, closed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS attempts(code TEXT, uid INTEGER, answers TEXT, submitted REAL, score INTEGER, wrong TEXT, notified INTEGER DEFAULT 0, PRIMARY KEY(code,uid));
            CREATE TABLE IF NOT EXISTS pending(token TEXT PRIMARY KEY, uid INTEGER, code TEXT, answers TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            ''')
    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            with c: yield c
        finally: c.close()
    def authorize(self, uid):
        if uid != self.admin: raise ValueError('Bu amal faqat administrator uchun.')
    def create(self, uid, key, delayed, deadline=None):
        self.authorize(uid)
        key = answers(key)
        if deadline is not None and deadline <= time.time(): raise ValueError('Muddat kelajakda bo‘lishi kerak.')
        with self.db() as c:
            while True:
                code = str(secrets.randbelow(90000000)+10000000)
                try:
                    c.execute('INSERT INTO tests(code,key,delayed,deadline) VALUES(?,?,?,?)', (code,key,int(delayed),deadline))
                    return code
                except sqlite3.IntegrityError: pass
    def close(self, uid, code):
        self.authorize(uid)
        with self.db() as c:
            if not c.execute('UPDATE tests SET closed=1 WHERE code=?',(code,)).rowcount: raise ValueError('Test topilmadi.')
    def expire(self):
        with self.db() as c: c.execute('UPDATE tests SET closed=1 WHERE deadline<=?',(time.time(),))
    def preview(self, uid, text):
        parts = text.strip().split(maxsplit=1)
        if len(parts)!=2: raise ValueError('Kod va barcha javoblarni bitta xabarda yuboring: 482731 ABCDAB')
        code, key = parts[0], answers(parts[1])
        with self.db() as c:
            t = c.execute('SELECT * FROM tests WHERE code=?',(code,)).fetchone()
            self.check(t, key)
            if c.execute('SELECT 1 FROM attempts WHERE code=? AND uid=?',(code,uid)).fetchone(): raise ValueError('Siz bu testni topshirgansiz.')
            token=secrets.token_hex(12)
            c.execute('DELETE FROM pending WHERE created<?',(time.time()-1800,))
            c.execute('INSERT INTO pending VALUES(?,?,?,?,?)',(token,uid,code,key,time.time()))
            return token, code, key
    def check(self,t,key):
        if t is None: raise ValueError('Test topilmadi.')
        if t['closed'] or (t['deadline'] is not None and t['deadline']<=time.time()): raise ValueError('Test yopilgan.')
        if len(key)!=len(t['key']): raise ValueError(f'Javoblar soni {len(t["key"])} ta bo‘lishi kerak.')
    def confirm(self,uid,token):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            p=c.execute('SELECT * FROM pending WHERE token=? AND uid=?',(token,uid)).fetchone()
            if p is None or p['created']<time.time()-1800: raise ValueError('Tasdiqlash muddati tugagan. Qayta yuboring.')
            t=c.execute('SELECT * FROM tests WHERE code=?',(p['code'],)).fetchone()
            self.check(t,p['answers'])
            wrong=[i+1 for i,(a,b) in enumerate(zip(p['answers'],t['key'])) if a!=b]
            try: c.execute('INSERT INTO attempts(code,uid,answers,submitted,score,wrong) VALUES(?,?,?,?,?,?)',(p['code'],uid,p['answers'],time.time(),len(t['key'])-len(wrong),json.dumps(wrong)))
            except sqlite3.IntegrityError: raise ValueError('Siz bu testni topshirgansiz.')
            c.execute('DELETE FROM pending WHERE code=? AND uid=?',(p['code'],uid))
            return p['code']
    def history(self,uid,all_users=False):
        if all_users: self.authorize(uid)
        self.expire()
        with self.db() as c:
            rows=c.execute('SELECT a.*,t.delayed,t.closed FROM attempts a JOIN tests t USING(code) '+('' if all_users else 'WHERE uid=? ')+'ORDER BY submitted DESC',() if all_users else (uid,)).fetchall()
            result=[]
            for row in rows:
                r=dict(row)
                if not all_users and r['delayed'] and not r['closed']: r['score']=r['wrong']=None
                result.append(r)
            return result
    def tests(self,uid):
        self.authorize(uid)
        self.expire()
        with self.db() as c: return [dict(r) for r in c.execute('SELECT code,deadline,closed,delayed FROM tests ORDER BY rowid DESC')]

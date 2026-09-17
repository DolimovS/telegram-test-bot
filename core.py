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
            CREATE TABLE IF NOT EXISTS retired_codes(code TEXT PRIMARY KEY);
            ''')
            if 'archived' not in {r['name'] for r in c.execute('PRAGMA table_info(tests)')}:
                c.execute('ALTER TABLE tests ADD COLUMN archived INTEGER NOT NULL DEFAULT 0')
            c.execute('CREATE INDEX IF NOT EXISTS attempts_code ON attempts(code)')
            c.execute('CREATE INDEX IF NOT EXISTS tests_archived ON tests(archived)')
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
            c.execute('BEGIN IMMEDIATE')
            used = {row['code'] for row in c.execute('SELECT code FROM tests UNION SELECT code FROM retired_codes')}
            available = [str(n) for n in range(1000, 10000) if str(n) not in used]
            if not available:
                raise ValueError('Barcha 4 xonali test kodlari band. Yangi test yaratib bo‘lmaydi.')
            code = secrets.choice(available)
            c.execute('INSERT INTO tests(code,key,delayed,deadline) VALUES(?,?,?,?)', (code,key,int(delayed),deadline))
            return code
    def close(self, uid, code):
        self.authorize(uid)
        with self.db() as c:
            if not c.execute('UPDATE tests SET closed=1 WHERE code=?',(code,)).rowcount: raise ValueError('Test topilmadi.')
    def expire(self):
        with self.db() as c: c.execute('UPDATE tests SET closed=1 WHERE deadline<=?',(time.time(),))
    def preview(self, uid, text):
        parts = text.strip().split(maxsplit=1)
        if len(parts)!=2: raise ValueError('Kod va barcha javoblarni bitta xabarda yuboring: 4827 ABCDAB')
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
        if t['archived']: raise ValueError('Test arxivlangan. Javob qabul qilinmaydi.')
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

    def manage_tests(self, uid, archived=False, page=0, size=5):
        self.authorize(uid)
        self.expire()
        with self.db() as c:
            total=c.execute('SELECT COUNT(*) FROM tests WHERE archived=?',(int(archived),)).fetchone()[0]
            pages=max(1,(total+size-1)//size)
            page=min(max(0,page),pages-1)
            rows=c.execute('SELECT t.code,t.deadline,t.closed,t.delayed,t.archived,(SELECT COUNT(*) FROM attempts a WHERE a.code=t.code) AS submissions FROM tests t WHERE t.archived=? ORDER BY t.rowid DESC LIMIT ? OFFSET ?', (int(archived),size,page*size)).fetchall()
            return [dict(r) for r in rows],page,pages,total

    def test_details(self,uid,code):
        self.authorize(uid)
        self.expire()
        with self.db() as c:
            row=c.execute('SELECT code,deadline,closed,delayed,archived,(SELECT COUNT(*) FROM attempts a WHERE a.code=t.code) AS submissions FROM tests t WHERE code=?',(code,)).fetchone()
            if row is None: raise ValueError('Test topilmadi.')
            return dict(row)

    def archive(self,uid,code):
        self.authorize(uid)
        with self.db() as c:
            if not c.execute('UPDATE tests SET archived=1,closed=1 WHERE code=?',(code,)).rowcount:
                raise ValueError('Test topilmadi.')

    def unarchive(self,uid,code):
        self.authorize(uid)
        with self.db() as c:
            if not c.execute('UPDATE tests SET archived=0 WHERE code=?',(code,)).rowcount:
                raise ValueError('Test topilmadi.')

    def delete_empty(self,uid,code):
        self.authorize(uid)
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM tests WHERE code=?',(code,)).fetchone():
                raise ValueError('Test topilmadi.')
            if c.execute('SELECT 1 FROM attempts WHERE code=? LIMIT 1',(code,)).fetchone():
                raise ValueError('Bu testda topshirishlar bor. Tarixni saqlash uchun testni arxivlang.')
            c.execute('INSERT OR IGNORE INTO retired_codes(code) VALUES(?)',(code,))
            c.execute('DELETE FROM pending WHERE code=?',(code,))
            c.execute('DELETE FROM tests WHERE code=?',(code,))

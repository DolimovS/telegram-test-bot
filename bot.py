import os, json, time, logging, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from core import Store

TZ=timezone(timedelta(hours=5), 'Asia/Tashkent')
def stamp(value): return datetime.fromtimestamp(value,TZ).strftime('%Y-%m-%d %H:%M')
def render(r):
    result='Natija test yopilganda ochiladi.' if r['score'] is None else f"To‘g‘ri: {r['score']}/{len(r['answers'])}. Xato savollar: {', '.join(map(str,json.loads(r['wrong']))) or 'yo‘q'}."
    return f"Kod: {r['code']} | ID: {r['uid']}\nJavoblar: {r['answers']}\nSana: {stamp(r['submitted'])}\n{result}"

class Bot:
    def __init__(self,token,store): self.token,self.s=token,store
    def api(self,method,**data):
        req=urllib.request.Request('https://api.telegram.org/bot'+self.token+'/'+method,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response: result=json.load(response)
        if not result.get('ok'): raise RuntimeError('Telegram API xatosi')
        return result['result']
    def send(self,uid,text,buttons=None):
        for start in range(0,len(text),3500):
            kwargs={'chat_id':uid,'text':text[start:start+3500]}
            if buttons and start+3500>=len(text): kwargs['reply_markup']={'inline_keyboard':buttons}
            self.api('sendMessage',**kwargs)
    def menu(self,uid):
        buttons=[[{'text':'Mening tarixim','callback_data':'history'}]]
        if uid==self.s.admin: buttons += [[{'text':'Test yaratish','callback_data':'new'},{'text':'Testlar','callback_data':'tests'}],[{'text':'Barcha natijalar','callback_data':'all'}]]
        self.send(uid,'Kod va barcha javoblarni bitta xabarda yuboring.\nMisol: 482731 ABCDAB\nYoki: 482731 1-A, 2-B, 3-C\nTasdiqlangandan keyin javoblar o‘zgarmaydi.',buttons)
    def handle(self,u):
        cb=u.get('callback_query')
        m=cb.get('message',{}) if cb else u.get('message',{})
        if m.get('chat',{}).get('type')!='private':
            if cb: self.api('answerCallbackQuery',callback_query_id=cb['id'],text='Faqat shaxsiy chatda ishlaydi.')
            return
        uid=(cb or m)['from']['id']
        if m['chat']['id']!=uid: return
        try:
            if cb:
                self.api('answerCallbackQuery',callback_query_id=cb['id'])
                action=cb.get('data','')
                if action.startswith('ok:'):
                    code=self.s.confirm(uid,action[3:])
                    row=next(r for r in self.s.history(uid) if r['code']==code)
                    self.send(uid,'Javoblar qabul qilindi.\n'+render(row))
                elif action.startswith('cancel:'):
                    with self.s.db() as c: c.execute('DELETE FROM pending WHERE token=? AND uid=?',(action[7:],uid))
                    self.send(uid,'Tasdiqlanmadi. Javoblarni qayta yuborishingiz mumkin.')
                elif action in ('history','all'):
                    rows=self.s.history(uid,action=='all')
                    if not rows: self.send(uid,'Tarix hozircha bo‘sh.')
                    for r in rows: self.send(uid,render(r))
                else:
                    self.s.authorize(uid)
                    if action=='new': self.send(uid,'Natija rejimini tanlang:',[[{'text':'Darhol','callback_data':'mode:0'},{'text':'Yopilganda','callback_data':'mode:1'}]])
                    elif action.startswith('mode:'):
                        mode=int(action[5:])
                        if mode not in (0,1): raise ValueError('Noto‘g‘ri rejim.')
                        with self.s.db() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('draft',str(mode)))
                        self.send(uid,'Kalit va muddatni yuboring:\nABCDAB | 2026-12-31 18:00\nMuddat kerak bo‘lmasa: ABCDAB | yo‘q\nVaqt: Asia/Tashkent. Har bir yaratishda yangi kod beriladi.')
                    elif action=='tests':
                        for t in self.s.tests(uid):
                            self.send(uid,f"Kod: {t['code']} | {'Yopiq' if t['closed'] else 'Ochiq'}\nMuddat: {stamp(t['deadline']) if t['deadline'] else 'yo‘q'}",None if t['closed'] else [[{'text':'Testni yopish','callback_data':'close:'+t['code']}]])
                    elif action.startswith('close:'):
                        self.s.close(uid,action[6:]); self.send(uid,'Test yopildi. Kechiktirilgan natijalar ochildi.')
            else:
                text=m.get('text','').strip()
                if text in ('/start','/admin','/cancel'): 
                    if uid==self.s.admin:
                        with self.s.db() as c: c.execute("DELETE FROM settings WHERE key='draft'")
                    self.menu(uid); return
                if uid==self.s.admin and '|' in text:
                    self.s.authorize(uid)
                    with self.s.db() as c: draft=c.execute("SELECT value FROM settings WHERE key='draft'").fetchone()
                    if not draft: raise ValueError('Avval Test yaratish tugmasini bosing.')
                    key,when=map(str.strip,text.split('|',1))
                    deadline=None if when.lower() in ('yo‘q',"yo'q",'yoq','-') else datetime.strptime(when,'%Y-%m-%d %H:%M').replace(tzinfo=TZ).timestamp()
                    code=self.s.create(uid,key,int(draft['value']),deadline)
                    with self.s.db() as c: c.execute("DELETE FROM settings WHERE key='draft'")
                    self.send(uid,f'Test yaratildi. Kod: {code}'); return
                token,code,key=self.s.preview(uid,text)
                self.send(uid,f"Kod: {code}\n"+' '.join(f'{i}-{a}' for i,a in enumerate(key,1))+'\nYakuniy topshirishni tasdiqlaysizmi?',[[{'text':'Tasdiqlash','callback_data':'ok:'+token},{'text':'Bekor qilish','callback_data':'cancel:'+token}]])
        except ValueError as e: self.send(uid,str(e))
    def notify(self):
        self.s.expire()
        with self.s.db() as c: rows=c.execute('SELECT a.*,t.delayed,t.closed FROM attempts a JOIN tests t USING(code) WHERE a.notified=0 AND (t.closed=1 OR t.delayed=0)').fetchall()
        for r in rows:
            try: self.send(r['uid'],render(dict(r)))
            except urllib.error.HTTPError as e:
                if e.code not in (400,403): raise
            else:
                with self.s.db() as c: c.execute('UPDATE attempts SET notified=1 WHERE code=? AND uid=?',(r['code'],r['uid']))
    def run(self):
        with self.s.db() as c: row=c.execute("SELECT value FROM settings WHERE key='offset'").fetchone()
        offset=int(row['value']) if row else 0
        while True:
            try:
                self.notify()
                for u in self.api('getUpdates',offset=offset,timeout=20,allowed_updates=['message','callback_query']):
                    self.handle(u)
                    offset=u['update_id']+1
                    with self.s.db() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('offset',str(offset)))
            except Exception as e:
                logging.error('Aloqa/ishlash xatosi: %s',type(e).__name__)
                time.sleep(5)

if __name__=='__main__':
    for line in Path('.env').read_text(encoding='utf-8').splitlines() if Path('.env').exists() else []:
        if line.strip() and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); os.environ.setdefault(k.strip(),v.strip())
    token=os.environ.get('BOT_TOKEN','')
    admin=os.environ.get('ADMIN_ID','')
    if not token or token=='replace_me' or not admin.isdigit() or int(admin)<=0:
        raise SystemExit('.env ichida BOT_TOKEN va musbat raqamli ADMIN_ID ni lokal sozlang.')
    Bot(token,Store(os.environ.get('DB_PATH','bot.sqlite3'),int(admin))).run()

import os, json, time, logging, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from core import Store

TZ=timezone(timedelta(hours=5), 'Asia/Tashkent')
def stamp(value): return datetime.fromtimestamp(value,TZ).strftime('%Y-%m-%d %H:%M')
from presentation import render, preview, chunks, NAV

class Bot:
    def __init__(self,token,store): self.token,self.s=token,store
    def api(self,method,**data):
        req=urllib.request.Request('https://api.telegram.org/bot'+self.token+'/'+method,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response: result=json.load(response)
        if not result.get('ok'): raise RuntimeError('Telegram API xatosi')
        return result['result']
    def send(self,uid,text,buttons=None):
        parts = list(chunks(text))
        for index, part in enumerate(parts):
            kwargs = {'chat_id': uid, 'text': part}
            if buttons and index == len(parts)-1:
                kwargs['reply_markup'] = buttons if isinstance(buttons,dict) else {'inline_keyboard': buttons}
            while True:
                try:
                    self.api('sendMessage', **kwargs)
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 429: raise
                    try: delay = json.load(e).get('parameters', {}).get('retry_after', 2)
                    except Exception: delay = 2
                    time.sleep(max(1, min(int(delay), 60)))
            if index < len(parts)-1: time.sleep(1.1)
    def menu(self,uid):
        self.send(uid,'▶️ Boshlash — bosh menyu\nQuyidagi tugma orqali istalgan payt menyuga qaytishingiz mumkin.',
                  {'keyboard':[[{'text':'▶️ Boshlash'},{'text':'📚 Mening tarixim'}]],'resize_keyboard':True,'is_persistent':True})
        buttons=[[{'text':'▶️ Boshlash','callback_data':'menu'},{'text':'📚 Mening tarixim','callback_data':'history'}]]
        if uid==self.s.admin: buttons += [[{'text':'➕ Test yaratish','callback_data':'new'},{'text':'Testlar','callback_data':'tests'}],[{'text':'📊 Barcha natijalar','callback_data':'all'}]]
        self.send(uid,'🎓 TEST MARKAZI\n\nKod va barcha javoblarni bitta xabarda yuboring.\nMisol: 4827 ABCDAB\nYoki: 4827 1-A, 2-B, 3-C\nTasdiqlangandan keyin javoblar o‘zgarmaydi.',buttons)
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
                    self.send(uid,'📩 Javoblar qabul qilindi.\n\n'+render(row), NAV)
                    if row['score'] is not None:
                        with self.s.db() as c: c.execute('UPDATE attempts SET notified=1 WHERE code=? AND uid=?',(code,uid))
                elif action.startswith('cancel:'):
                    with self.s.db() as c: c.execute('DELETE FROM pending WHERE token=? AND uid=?',(action[7:],uid))
                    self.send(uid,'Tasdiqlanmadi. Javoblarni qayta yuborishingiz mumkin.')
                elif action == 'menu': self.menu(uid)
                elif action.split(':')[0] in ('history','all'):
                    kind = action.split(':')[0]
                    page = int(action.split(':')[1]) if ':' in action else 0
                    self.show_history(uid,kind,page)
                else:
                    self.s.authorize(uid)
                    if action=='new': self.send(uid,'Natija rejimini tanlang:',[[{'text':'Darhol','callback_data':'mode:0'},{'text':'Yopilganda','callback_data':'mode:1'}]])
                    elif action.startswith('mode:'):
                        mode=int(action[5:])
                        if mode not in (0,1): raise ValueError('Noto‘g‘ri rejim.')
                        with self.s.db() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('draft',str(mode)))
                        self.send(uid,'Kalit va muddatni yuboring:\nABCDAB | 2026-12-31 18:00\nMuddat kerak bo‘lmasa: ABCDAB | yo‘q\nVaqt: Asia/Tashkent. Har bir yaratishda yangi kod beriladi.')
                    elif action=='tests' or action.startswith('tests:'):
                        bits=action.split(':')
                        archived=len(bits)>1 and bits[1]=='archive'
                        page=int(bits[2]) if len(bits)>2 else 0
                        self.manage_tests(uid,archived,page)
                    elif action.startswith('test:'):
                        self.show_test(uid,action[5:])
                    elif action.startswith('archive:'):
                        code=action[8:]
                        self.s.archive(uid,code)
                        self.send(uid,'📦 Test arxivlandi va yopildi. Tarix saqlandi; kechiktirilgan natijalar ochildi.')
                        self.show_test(uid,code)
                    elif action.startswith('unarchive:'):
                        code=action[10:]
                        self.s.unarchive(uid,code)
                        self.send(uid,'↩️ Test asosiy ro‘yxatga qaytarildi. Test yopiq qoladi; qayta topshirish ochilmaydi.')
                        self.show_test(uid,code)
                    elif action.startswith('delete:'):
                        code=action[7:]
                        detail=self.s.test_details(uid,code)
                        if detail['submissions']:
                            self.send(uid,'Bu testda topshirishlar bor. O‘chirish mumkin emas; tarixni saqlash uchun arxivlang.',
                                      [[{'text':'📦 Arxivlash','callback_data':'archive:'+code},{'text':'⬅️ Testga qaytish','callback_data':'test:'+code}]])
                        else:
                            self.send(uid,f'🗑 {code} testini butunlay o‘chirasizmi?\nTasdiqlangan topshirish yo‘q. Bu amalni qaytarib bo‘lmaydi. Kod qayta ishlatilmaydi.',
                                      [[{'text':'🗑 Ha, o‘chirish','callback_data':'delete_yes:'+code},{'text':'Bekor qilish','callback_data':'test:'+code}]])
                    elif action.startswith('delete_yes:'):
                        code=action[11:]
                        try:
                            self.s.delete_empty(uid,code)
                        except ValueError as error:
                            self.send(uid,str(error),[[{'text':'📦 Arxivlash','callback_data':'archive:'+code},{'text':'Testlar','callback_data':'tests'}]])
                        else:
                            self.send(uid,'🗑 Bo‘sh test o‘chirildi. Uning kodi qayta ishlatilmaydi.')
                            self.manage_tests(uid)
                    elif action.startswith('close:'):
                        self.s.close(uid,action[6:]); self.send(uid,'Test yopildi. Kechiktirilgan natijalar ochildi.')
                        self.show_test(uid,action[6:])
            else:
                text=m.get('text','').strip()
                if text=='📚 Mening tarixim':
                    self.show_history(uid)
                    return
                if text in ('/start','/admin','/cancel','▶️ Boshlash','Boshlash'): 
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
                self.send(uid,preview(code,key),[[{'text':'Tasdiqlash','callback_data':'ok:'+token},{'text':'Bekor qilish','callback_data':'cancel:'+token}]])
        except ValueError as e: self.send(uid,str(e))

    def show_history(self,uid,kind='history',page=0):
        rows=self.s.history(uid,kind=='all')
        pages=max(1,(len(rows)+2)//3)
        page=min(max(0,page),pages-1)
        for row in rows[page*3:page*3+3]: self.send(uid,render(row))
        nav=[]
        if page: nav.append({'text':'⬅️ Oldingi','callback_data':f'{kind}:{page-1}'})
        if page+1<pages: nav.append({'text':'Keyingi ➡️','callback_data':f'{kind}:{page+1}'})
        buttons=([nav] if nav else [])+[[{'text':'▶️ Boshlash','callback_data':'menu'}]]
        self.send(uid,f'📚 Tarix · {page+1}/{pages} sahifa · {len(rows)} ta topshirish' if rows else '📚 Tarix hozircha bo‘sh.',buttons)

    def manage_tests(self,uid,archived=False,page=0):
        rows,page,pages,total=self.s.manage_tests(uid,archived,page)
        buttons=[]
        for row in rows:
            status='📦 Arxiv' if row['archived'] else '🔒 Yopiq' if row['closed'] else '🟢 Ochiq'
            buttons.append([{'text':f"{row['code']} · {status} · {row['submissions']} ta topshirish",'callback_data':'test:'+row['code']}])
        group='archive' if archived else 'active'
        nav=[]
        if page: nav.append({'text':'⬅️ Oldingi','callback_data':f'tests:{group}:{page-1}'})
        if page+1<pages: nav.append({'text':'Keyingi ➡️','callback_data':f'tests:{group}:{page+1}'})
        if nav: buttons.append(nav)
        buttons.append([{'text':'📝 Asosiy testlar' if archived else '📦 Arxiv','callback_data':'tests:active:0' if archived else 'tests:archive:0'}])
        buttons.append([{'text':'➕ Test yaratish','callback_data':'new'},{'text':'▶️ Boshlash','callback_data':'menu'}])
        self.send(uid,f"{'📦 ARXIV' if archived else '📝 TESTLARNI BOSHQARISH'}\n{total} ta test · {page+1}/{pages} sahifa\nBoshqarish uchun testni tanlang.",buttons)

    def show_test(self,uid,code):
        t=self.s.test_details(uid,code)
        status='Arxivlangan' if t['archived'] else 'Yopiq' if t['closed'] else 'Ochiq'
        buttons=[]
        if not t['closed'] and not t['archived']: buttons.append([{'text':'🔒 Testni yopish','callback_data':'close:'+code}])
        buttons.append([{'text':'↩️ Arxivdan qaytarish' if t['archived'] else '📦 Arxivlash','callback_data':('unarchive:' if t['archived'] else 'archive:')+code}])
        if not t['submissions']: buttons.append([{'text':'🗑 Butunlay o‘chirish','callback_data':'delete:'+code}])
        buttons.append([{'text':'⬅️ Testlar','callback_data':'tests:archive:0' if t['archived'] else 'tests'},{'text':'▶️ Boshlash','callback_data':'menu'}])
        self.send(uid,f"📝 Test kodi: {code}\nHolat: {status}\nTopshirishlar: {t['submissions']} ta\nMuddat: {stamp(t['deadline']) if t['deadline'] else 'yo‘q'}\nNatija: {'Yopilganda' if t['delayed'] else 'Darhol'}\n\nArxivlash tarixni saqlaydi va testni yopadi.",buttons)
    def notify(self):
        self.s.expire()
        with self.s.db() as c: rows=c.execute('SELECT a.*,t.delayed,t.closed FROM attempts a JOIN tests t USING(code) WHERE a.notified=0 AND (t.closed=1 OR t.delayed=0)').fetchall()
        for r in rows:
            try: self.send(r['uid'],render(dict(r)), NAV)
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

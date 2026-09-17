import {UserError,button,NAV,messages,render,preview,parseDeadline,stamp} from './presentation.js';

export function menu(uid,admin) {
  const buttons=[[button('▶️ Boshlash','menu'),button('📚 Mening tarixim','history')]];
  if(uid===admin) buttons.push([button('➕ Test yaratish','new'),button('Testlar','tests')],[button('📊 Barcha natijalar','all')]);
  return messages(uid,'🎓 TEST MARKAZI\n\nKod va barcha javoblarni bitta xabarda yuboring.\nMisol: 4827 ABCDAB\nYoki: 4827 1-A, 2-B, 3-C\n\nTasdiqlangandan keyin javoblar o‘zgarmaydi.',buttons);
}
export function identity(update) {
  const cb=update.callback_query, message=cb?.message||update.message;
  const uid=(cb||message)?.from?.id;
  if(message?.chat?.type!=='private' || !Number.isSafeInteger(uid) || uid<=0 || message.chat.id!==uid) return null;
  return {uid,cb,message};
}
export async function handle(update,store) {
  const who=identity(update);
  if(!who) return [];
  const {uid,cb,message}=who, source=String(update.update_id);
  try {
    if(cb) {
      const action=cb.data||'';
      if(action==='menu') return menu(uid,store.admin);
      if(action.startsWith('ok:')) {
        const code=await store.confirm(uid,action.slice(3));
        // Released results are delivered by the durable result outbox, never twice here.
        const row=await store.result(uid,code);
        return row.score===null ? messages(uid,'📩 Javoblar qabul qilindi.\n\n'+render(row),NAV)
          : messages(uid,'📩 Javoblar qabul qilindi. Natijangiz tayyorlanmoqda.',NAV);
      }
      if(action.startsWith('cancel:')) {
        await store.q('DELETE FROM pending WHERE token=? AND uid=?',action.slice(7),uid).run();
        return messages(uid,'Tasdiqlanmadi. Javoblarni qayta yuborishingiz mumkin.',NAV);
      }
      if(/^(history|all)(:\d+)?$/.test(action)) {
        const [kind,p]=action.split(':'),page=Math.min(Number(p||0),1000000);
        const {rows,more}=await store.history(uid,kind==='all',page);
        const navigation=[];
        if(page) navigation.push(button('⬅️ Oldingi',`${kind}:${page-1}`));
        if(more) navigation.push(button('Keyingi ➡️',`${kind}:${page+1}`));
        return [...rows.flatMap(rendered=>messages(uid,render(rendered))),...messages(uid,rows.length?`📚 Tarix · ${page+1}-sahifa`:'📚 Tarix hozircha bo‘sh.',[...(navigation.length?[navigation]:[]),[button('🏠 Bosh menyu','menu')]])];
      }
      store.authorize(uid);
      if(action==='new') return messages(uid,'Natija rejimini tanlang:',[[button('Darhol','mode:0'),button('Yopilganda','mode:1')]]);
      if(/^mode:[01]$/.test(action)) {
        await store.q("INSERT INTO settings(key,value) VALUES('draft',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",action.slice(5)).run();
        return messages(uid,"Kalit va muddatni yuboring:\nABCDAB | 2026-12-31 18:00\n\nMuddat kerak bo‘lmasa: ABCDAB | yo‘q\nVaqt: Toshkent. Har bir yangi testga yangi kod beriladi.");
      }
      if(/^tests:(active|archive):\d+$/.test(action)||action==='tests') {
        const parts=action.split(':'), archived=parts[1]==='archive',page=Math.min(Number(parts[2]||0),1000000);
        const {rows,more}=await store.tests(uid,page,archived), nav=[];
        const kind=archived?'archive':'active';
        if(page) nav.push(button('⬅️ Oldingi',`tests:${kind}:${page-1}`));
        if(more) nav.push(button('Keyingi ➡️',`tests:${kind}:${page+1}`));
        const list=rows.map(t=>[button(`${t.code} · ${t.archived?'📦':t.closed?'🔒':'🟢'} · ${t.submissions} ta`,`test:${t.code}`)]);
        return messages(uid,`${archived?'📦 ARXIV':'📝 TESTLAR'} · ${page+1}-sahifa`,[...list,...(nav.length?[nav]:[]),[button(archived?'📝 Asosiy testlar':'📦 Arxiv',archived?'tests:active:0':'tests:archive:0')],[button('▶️ Boshlash','menu')]]);
      }
      if(action.startsWith('test:')) {const t=await store.details(uid,action.slice(5));return testCard(uid,t);}
      if(action.startsWith('archive:')) {const code=action.slice(8);await store.archive(uid,code);return [...messages(uid,'📦 Test arxivlandi. Tarix saqlandi.'),...testCard(uid,await store.details(uid,code))];}
      if(action.startsWith('unarchive:')) {const code=action.slice(10);await store.unarchive(uid,code);return [...messages(uid,'↩️ Test asosiy ro‘yxatga qaytdi va yopiq qoladi.'),...testCard(uid,await store.details(uid,code))];}
      if(action.startsWith('delete:')) {const code=action.slice(7),t=await store.details(uid,code);if(t.submissions) throw new UserError('Bu testda topshirishlar bor. Tarixni saqlash uchun testni arxivlang.');return messages(uid,`🗑 ${code} testini butunlay o‘chirasizmi?`,[[button('🗑 Ha, o‘chirish','delete_yes:'+code),button('Bekor qilish','test:'+code)]]);}
      if(action.startsWith('delete_yes:')) {const code=action.slice(11);await store.deleteEmpty(uid,code);return messages(uid,'🗑 Bo‘sh test o‘chirildi. Kod qayta ishlatilmaydi.',[[button('Testlar','tests'),button('▶️ Boshlash','menu')]]);}
      if(action.startsWith('close:')) {
        await store.close(uid,action.slice(6));
        return messages(uid,'🔒 Test yopildi. Kechiktirilgan natijalar ochildi.',NAV);
      }
      throw new UserError('Tugma eskirgan. Bosh menyuni oching.');
    }
    const text=(message.text||'').trim();
    if(['/start','/admin','/cancel'].includes(text)) {
      if(uid===store.admin) await store.q("DELETE FROM settings WHERE key='draft'").run();
      return menu(uid,store.admin);
    }
    if(uid===store.admin && text.includes('|')) {
      store.authorize(uid);
      const existing=await store.q('SELECT code FROM tests WHERE source_update=?',source).first();
      if(existing) return messages(uid,`📝 Test yaratildi.\nKod: ${existing.code}`,NAV);
      const draft=await store.q("SELECT value FROM settings WHERE key='draft'").first();
      if(!draft) throw new UserError('Avval Test yaratish tugmasini bosing.');
      const [key,...rest]=text.split('|');
      const deadline=parseDeadline(rest.join('|').trim());
      const code=await store.create(uid,key.trim(),Number(draft.value),deadline,source);
      // Keep the selected mode so webhook retries cannot consume another draft.
      return messages(uid,`📝 Test yaratildi.\nKod: ${code}`,NAV);
    }
    const pending=await store.preview(uid,text,source);
    return messages(uid,preview(pending.code,pending.answers),[[button('Tasdiqlash','ok:'+pending.token),button('Bekor qilish','cancel:'+pending.token)]]);
  } catch(error) {
    if(error instanceof UserError) return messages(uid,error.message,NAV);
    throw error;
  }
}
function testCard(uid,t) {
  const actions=[];if(!t.closed&&!t.archived) actions.push([button('🔒 Testni yopish','close:'+t.code)]);
  actions.push([button(t.archived?'↩️ Arxivdan qaytarish':'📦 Arxivlash',(t.archived?'unarchive:':'archive:')+t.code)]);
  if(!t.submissions) actions.push([button('🗑 Butunlay o‘chirish','delete:'+t.code)]);
  actions.push([button('⬅️ Testlar',t.archived?'tests:archive:0':'tests'),button('▶️ Boshlash','menu')]);
  return messages(uid,`📝 Test: ${t.code}\nHolat: ${t.archived?'Arxivlangan':t.closed?'Yopiq':'Ochiq'}\nTopshirishlar: ${t.submissions}\nMuddat: ${t.deadline?stamp(t.deadline):'yo‘q'}`,actions);
}

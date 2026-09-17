export class UserError extends Error {}
export const button = (text, callback_data) => ({text, callback_data});
export const NAV = [[button('📚 Mening tarixim','history'),button('🏠 Bosh menyu','menu')]];
export function stamp(value) {
  return new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Tashkent',dateStyle:'short',timeStyle:'short',hour12:false}).format(new Date(value*1000));
}
export function parseAnswers(input) {
  const text=input.trim().toUpperCase();
  if (/^[ABCD]+$/.test(text)) return text;
  const found=new Map();
  for (const part of text.split(/[,;\s]+/)) {
    const m=/^([1-9]\d*)[-.:]([ABCD])$/.exec(part);
    if (!m || !Number.isSafeInteger(Number(m[1])) || found.has(Number(m[1]))) throw new UserError('Javoblar formati xato yoki raqam takrorlangan.');
    found.set(Number(m[1]),m[2]);
  }
  let result='';
  for(let i=1;i<=found.size;i++) {
    if (!found.has(i)) throw new UserError('Savol raqamlari ketma-ket va to‘liq bo‘lishi kerak.');
    result+=found.get(i);
  }
  return result;
}
export function parseDeadline(text, now=Date.now()/1000) {
  if (["yo'q",'yo‘q','yoq','-'].includes(text.toLowerCase())) return null;
  if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(text)) throw new UserError('Sana formati: YYYY-MM-DD HH:MM (Toshkent).');
  const ms=Date.parse(text.replace(' ','T')+':00+05:00');
  if (!Number.isFinite(ms) || new Date(ms+5*3600000).toISOString().slice(0,16).replace('T',' ')!==text) throw new UserError('Sana yoki vaqt noto‘g‘ri.');
  if (ms/1000<=now) throw new UserError('Muddat kelajakda bo‘lishi kerak.');
  return ms/1000;
}
export function choices(answers, wrong=null) {
  return Array.from(answers,(letter,i)=>`${i+1}. ${letter}${wrong===null?'':wrong.has(i+1)?' ❌':' ✅'}`).join('\n');
}
export function render(row) {
  const visible=row.score!==null;
  const lines=[visible?'📊 TEST NATIJASI':'🔒 NATIJA KUTILMOQDA',`Test kodi: ${row.code}`,`👤 Telegram ID: ${row.uid}`,`🗓 ${stamp(row.submitted)} (Toshkent)`,''];
  if(visible) {
    lines.push(`🏆 Ball: ${row.score} / ${row.answers.length} · ${(row.score/row.answers.length*100).toFixed(1)}%`,`To‘g‘ri: ${row.score}   |   Xato: ${row.answers.length-row.score}`,'','SIZNING JAVOBLARINGIZ',choices(row.answers,new Set(JSON.parse(row.wrong))));
  } else lines.push('Javoblaringiz saqlandi. Natija test yopilganda ochiladi.','','SIZNING JAVOBLARINGIZ',choices(row.answers));
  return lines.join('\n');
}
export function preview(code,answers) {
  return `📝 JAVOBLARNI TEKSHIRING\nTest kodi: ${code}\nSavollar: ${answers.length} ta\n\n${choices(answers)}\n\nYakuniy topshirishni tasdiqlaysizmi?\nTasdiqlangach, javoblarni o‘zgartirib bo‘lmaydi.`;
}
export function chunks(text,limit=3500) {
  const result=[]; let current='';
  for(const line of text.match(/[^\n]*\n|[^\n]+$/g)||[]) {
    if(current && current.length+line.length>limit) {result.push(current);current='';}
    if(line.length<=limit) current+=line;
    else for(const char of line) {
      if(current.length+char.length>limit) {result.push(current);current='';}
      current+=char;
    }
  }
  if(current) result.push(current);
  return result;
}
export function messages(uid,text,buttons=null) {
  return chunks(text).map((part,i,parts)=>({chat_id:uid,text:part,...(buttons&&i===parts.length-1?{reply_markup:{inline_keyboard:buttons}}:{})}));
}

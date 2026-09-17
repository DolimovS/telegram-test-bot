import test from 'node:test';
import assert from 'node:assert/strict';
import {TestDB} from './db.js';
import {Store} from '../src/store.js';
import {parseAnswers,parseDeadline,render,preview,chunks,messages,NAV} from '../src/presentation.js';
import {handle} from '../src/handler.js';
import worker,{processUpdate,flushOutbox} from '../src/worker.js';

const setup=()=>new Store(new TestDB(),1);
const message=(id,uid,text)=>({update_id:id,message:{from:{id:uid},chat:{id:uid,type:'private'},text}});
const callback=(id,uid,data)=>({update_id:id,callback_query:{id:'cb'+id,from:{id:uid},message:{chat:{id:uid,type:'private'}},data}});
test('parsing supports both formats, rejects missing/duplicate/invalid numbers',()=>{
  assert.equal(parseAnswers('aBcD'),'ABCD');assert.equal(parseAnswers('2-b,1:A 3.C'),'ABC');
  for(const text of ['','1-A 1-B','1-A 3-C','0-A','ABCE','1-A,2-E']) assert.throws(()=>parseAnswers(text));
});
test('Tashkent deadline is unambiguous and invalid calendar dates fail',()=>{
  assert.equal(parseDeadline('2030-01-01 05:00'),Date.parse('2030-01-01T00:00:00Z')/1000);
  assert.equal(parseDeadline("yo'q"),null);
  assert.throws(()=>parseDeadline('2030-02-30 12:00'));
  assert.throws(()=>parseDeadline('2000-01-01 12:00'));
});
test('four digit codes: concurrent uniqueness and idempotent creation',async()=>{
  const s=setup();const codes=await Promise.all(Array.from({length:20},(_,i)=>s.create(1,'A',0,null,String(i))));
  assert.equal(new Set(codes).size,20);for(const c of codes) assert.match(c,/^[1-9]\d{3}$/);
  assert.equal(await s.create(1,'A',0,null,'0'),codes[0]);
});
test('old codes preserved; closed codes never reused; namespace exhaustion fails',async()=>{
  const s=setup();s.db.raw.exec("INSERT INTO tests(code,key,delayed,closed) VALUES('1000','A',0,1),('12345678','A',0,0)");
  assert.equal(await s.create(1,'A',0,null,'x'),'1001');
  const p=await s.preview(2,'12345678 A','p');assert.equal(await s.confirm(2,p.token),'12345678');
  s.db.raw.exec("INSERT OR IGNORE INTO tests(code,key,delayed) SELECT code,'A',0 FROM available_codes");
  await assert.rejects(s.create(1,'A',0,null,'full'),/Barcha 4 xonali/);
});
test('admin operations reject other identities at storage and callback layers',async()=>{
  const s=setup();
  for(const task of [()=>s.create(2,'A',0,null,'x'),()=>s.close(2,'1000'),()=>s.tests(2),()=>s.history(2,true)]) await assert.rejects(task(),/administrator/);
  for(const action of ['mode:1','new','tests','all','close:1000']) {
    const result=await handle(callback(1,2,action),s);assert.match(result[0].text,/administrator/);
  }
  assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM settings').get().n,0);
});
test('groups and forged private chat identity produce no operation',async()=>{
  const s=setup(),u=message(1,1,'/start');u.message.chat.type='group';assert.deepEqual(await handle(u,s),[]);
  u.message.chat.type='private';u.message.chat.id=2;assert.deepEqual(await handle(u,s),[]);
});
test('one atomic confirmed attempt across parallel confirmations',async()=>{
  const s=setup(),code=await s.create(1,'AB',0,null,'test');
  const ps=await Promise.all(Array.from({length:10},(_,i)=>s.preview(2,code+' AC','p'+i)));
  await Promise.all(ps.map(p=>s.confirm(2,p.token)));
  assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM attempts').get().n,1);
  assert.equal((await s.result(2,code)).score,1);
  await assert.rejects(s.preview(2,code+' AB','other'),/topshirgansiz/);
});
test('pending confirmation belongs only to its user, count validation and cancellation',async()=>{
  const s=setup(),code=await s.create(1,'AB',0,null,'test');
  await assert.rejects(s.preview(2,code+' A','bad'),/soni/);
  const p=await s.preview(2,code+' AB','p');await assert.rejects(s.confirm(3,p.token));
  await handle(callback(9,3,'cancel:'+p.token),s);assert.ok(await s.q('SELECT * FROM pending WHERE token=?',p.token).first());
  await handle(callback(10,2,'cancel:'+p.token),s);await assert.rejects(s.confirm(2,p.token));
});
test('manual early closure, deadline and expired confirmation all block commit',async()=>{
  for(const mode of ['manual','deadline','pending']) {
    const s=setup(),code=await s.create(1,'A',1,Date.now()/1000+3600,'t'),p=await s.preview(2,code+' A','p');
    if(mode==='manual') await s.close(1,code);
    if(mode==='deadline') await s.q('UPDATE tests SET deadline=unixepoch()-1').run();
    if(mode==='pending') await s.q('UPDATE pending SET created=unixepoch()-1801').run();
    await assert.rejects(s.confirm(2,p.token));
    assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM attempts').get().n,0);
  }
});
test('close racing between validation and insertion still prevents attempt',async()=>{
  const s=setup(),code=await s.create(1,'A',0,null,'t'),p=await s.preview(2,code+' A','p');
  const check=s.check.bind(s);s.check=(t,a)=>{check(t,a);s.db.raw.exec('UPDATE tests SET closed=1');};
  await assert.rejects(s.confirm(2,p.token));
});
test('delayed results are masked in history and released on closure; users isolated',async()=>{
  const s=setup(),code=await s.create(1,'AB',1,null,'t'),p=await s.preview(2,code+' AC','p');await s.confirm(2,p.token);
  const row=(await s.history(2)).rows[0];assert.equal(row.score,null);assert.equal(row.wrong,null);
  assert.doesNotMatch(render(row),/✅|❌|Ball:|%/);
  assert.equal((await s.history(3)).rows.length,0);
  assert.equal((await s.history(1,true)).rows[0].score,1);
  await s.notifications();assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM outbox').get().n,0);
  await s.close(1,code);await s.notifications();await s.notifications();
  assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM outbox').get().n,1);
  assert.match(render(await s.result(2,code)),/2\. C ❌/);
});
test('scheduled expiry releases delayed result',async()=>{
  const s=setup(),code=await s.create(1,'A',1,Date.now()/1000+3600,'t'),p=await s.preview(2,code+' A','p');await s.confirm(2,p.token);
  await s.q('UPDATE tests SET deadline=unixepoch()-1').run();await s.notifications();
  assert.equal((await s.result(2,code)).score,1);
  assert.equal(s.db.raw.prepare('SELECT closed FROM tests').get().closed,1);
});
test('result shows own answers, score and percentage; preview reveals no correctness',()=>{
  const row={code:'1234',uid:2,submitted:1,answers:'BA',score:1,wrong:'[2]'};
  const result=render(row);for(const text of ['1. B ✅','2. A ❌','50.0%','1 / 2']) assert.ok(result.includes(text));
  assert.doesNotMatch(result,/2\. [BCD]/);assert.doesNotMatch(preview('1234','BA'),/✅|❌|Ball:|%/);
});
test('long output is complete and UTF-16 safe with buttons on final part',()=>{
  const text=render({code:'1234',uid:2,submitted:1,answers:'A'.repeat(4096),score:4095,wrong:'[4096]'});
  const parts=chunks(text);assert.equal(parts.join(''),text);assert.ok(parts.every(p=>p.length<=3500));assert.ok(parts.at(-1).includes('4096. A ❌'));
  assert.equal(chunks('🎓'.repeat(5000)).join(''),'🎓'.repeat(5000));
  const payloads=messages(2,text,NAV);assert.equal(payloads[0].reply_markup,undefined);assert.ok(payloads.at(-1).reply_markup);
});
test('webhook retries do not create duplicate tests or outgoing acknowledgements',async()=>{
  const s=setup();await processUpdate(callback(1,1,'mode:0'),s);
  const u=message(2,1,"AB | yo'q");await processUpdate(u,s);await processUpdate(u,s);
  assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM tests').get().n,1);
  assert.equal(s.db.raw.prepare("SELECT COUNT(*) n FROM outbox WHERE id LIKE 'update:2:%'").get().n,1);
});
test('crash after test creation recovers on webhook retry without second test',async()=>{
  const s=setup();await processUpdate(callback(1,1,'mode:0'),s);
  const original=s.db.batch.bind(s.db);let fault=true;
  s.db.batch=async statements=>{if(fault&&statements.some(x=>x.sql.includes('UPDATE updates SET done'))) {fault=false;throw new Error('simulated');}return original(statements);};
  await assert.rejects(processUpdate(message(2,1,"AB | yo'q"),s));
  await processUpdate(message(2,1,"AB | yo'q"),s);
  assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM tests').get().n,1);
});
test('outbox retries rate limits; same-chat order and no duplicate successful delivery',async()=>{
  const s=setup();await s.db.batch(s.outboxStatements('x',messages(2,'A'.repeat(4000))));
  let calls=0;const fetcher=async()=>{calls++;return Response.json({ok:false,error_code:429,parameters:{retry_after:5}},{status:429});};
  await flushOutbox(s,{BOT_TOKEN:'test'},fetcher);assert.equal(calls,1);
  await s.q('UPDATE outbox SET retry_at=0').run();
  const sent=[];const success=async(_url,options)=>{sent.push(JSON.parse(options.body).text);return Response.json({ok:true,result:{}});};
  await flushOutbox(s,{BOT_TOKEN:'test'},success);await flushOutbox(s,{BOT_TOKEN:'test'},success);
  assert.equal(sent.join(''),'A'.repeat(4000));assert.equal(sent.length,2);
});
test('webhook validates secret, method, identity and configuration before writes',async()=>{
  const s=setup(),env={DB:s.db,ADMIN_ID:'1',BOT_TOKEN:'test',WEBHOOK_SECRET:'a'.repeat(40)},ctx={waitUntil(){}};
  assert.equal((await worker.fetch(new Request('https://bot/webhook',{method:'POST',body:'{}'}),env,ctx)).status,403);
  assert.equal((await worker.fetch(new Request('https://bot/webhook'),env,ctx)).status,405);
  const request=(body)=>new Request('https://bot/webhook',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':env.WEBHOOK_SECRET},body});
  assert.equal((await worker.fetch(request('bad'),env,ctx)).status,400);
  const group=message(1,2,'/start');group.message.chat.type='group';assert.equal((await worker.fetch(request(JSON.stringify(group)),env,ctx)).status,200);
  assert.equal(s.db.raw.prepare('SELECT COUNT(*) n FROM updates').get().n,0);
  assert.equal((await worker.fetch(request('{}'),{...env,ADMIN_ID:'replace_me'},ctx)).status,503);
});
test('start button, archive privacy, safe delete and pagination',async()=>{
  const s=setup();
  const menu=await handle(message(1,2,'/start'),s);assert.match(JSON.stringify(menu),/Boshlash/);
  const codes=[];for(let i=0;i<7;i++) codes.push(await s.create(1,'A',0,null,'m'+i));
  let p=await s.preview(2,codes[0]+' A','answer');await s.confirm(2,p.token);
  await s.archive(1,codes[0]);await assert.rejects(s.preview(3,codes[0]+' A','blocked'),/arxivlangan/);
  assert.equal((await s.history(2)).rows.length,1);
  await assert.rejects(s.deleteEmpty(1,codes[0]),/topshirishlar/);
  await s.unarchive(1,codes[0]);assert.equal((await s.details(1,codes[0])).closed,1);
  await s.deleteEmpty(1,codes[1]);assert.equal(await s.q('SELECT code FROM retired_codes WHERE code=?',codes[1]).first().then(Boolean),true);
  const first=await s.tests(1,0,false);assert.equal(first.rows.length,5);assert.equal(first.more,true);
  const second=await s.tests(1,1,false);assert.ok(second.rows.length>=1);
  for(const action of ['archive:'+codes[2],'unarchive:'+codes[2],'delete:'+codes[2],'delete_yes:'+codes[2],'test:'+codes[2],'tests:archive:0']) {
    const response=await handle(callback(100,3,action),s);assert.match(response[0].text,/administrator/);
  }
});

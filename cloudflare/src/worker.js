import {Store} from './store.js';
import {handle,identity} from './handler.js';

export function configured(env) {
  return Boolean(env.DB && env.BOT_TOKEN && env.BOT_TOKEN!=='replace_me'
    && /^\d+$/.test(String(env.ADMIN_ID)) && Number.isSafeInteger(Number(env.ADMIN_ID)) && Number(env.ADMIN_ID)>0
    && /^[A-Za-z0-9_-]{32,256}$/.test(env.WEBHOOK_SECRET||''));
}
async function equalSecret(a,b) {
  const hash=async text=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)));
  const [left,right]=await Promise.all([hash(a),hash(b)]);
  let diff=0;for(let i=0;i<left.length;i++) diff|=left[i]^right[i];
  return diff===0;
}
export async function processUpdate(update,store) {
  const owner=crypto.randomUUID();
  const claimed=await store.q(`INSERT INTO updates(id,lease,owner,created) VALUES(?,unixepoch()+60,?,unixepoch())
    ON CONFLICT(id) DO UPDATE SET lease=unixepoch()+60,owner=excluded.owner
    WHERE updates.done=0 AND updates.lease<unixepoch() RETURNING id`,update.update_id,owner).first();
  if(!claimed) {
    const row=await store.q('SELECT done FROM updates WHERE id=?',update.update_id).first();
    return Boolean(row?.done);
  }
  try {
    const payloads=await handle(update,store);
    await store.db.batch([...store.outboxStatements('update:'+update.update_id,payloads),
      store.q('UPDATE updates SET done=1 WHERE id=? AND owner=?',update.update_id,owner)]);
    return true;
  } catch(error) {
    await store.q('UPDATE updates SET lease=0 WHERE id=? AND owner=?',update.update_id,owner).run();
    throw error;
  }
}
export async function telegram(env,method,payload,fetcher=fetch) {
  // Do not log request URLs or Telegram's response bodies: they can contain credentials/content.
  const response=await fetcher(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(10000)
  });
  let data;
  try {data=await response.json();} catch {return {ok:false,error_code:response.status||502};}
  return {ok:Boolean(response.ok&&data.ok),error_code:data.error_code||response.status,retry_after:data.parameters?.retry_after};
}
export async function flushOutbox(store,env,fetcher=fetch,max=8) {
  for(let i=0;i<max;i++) {
    const owner=crypto.randomUUID();
    const row=await store.q(`UPDATE outbox SET lease=unixepoch()+45,owner=?
      WHERE id=(SELECT o.id FROM outbox o WHERE o.sent=0 AND o.retry_at<=unixepoch() AND o.lease<unixepoch()
        AND NOT EXISTS(SELECT 1 FROM outbox earlier WHERE earlier.uid=o.uid AND earlier.sent=0
          AND (earlier.created<o.created OR (earlier.created=o.created AND earlier.id<o.id)))
        ORDER BY o.created,o.id LIMIT 1) RETURNING *`,owner).first();
    if(!row) break;
    let result;
    try {result=await telegram(env,'sendMessage',JSON.parse(row.payload),fetcher);}
    catch {result={ok:false,error_code:502};}
    if(result.ok || result.error_code===403 || result.error_code===400) {
      await store.q('UPDATE outbox SET sent=?,lease=0 WHERE id=? AND owner=?',result.ok?1:2,row.id,owner).run();
    } else {
      const delay=Math.min(86400,Math.max(2,Number(result.retry_after)||30));
      await store.q('UPDATE outbox SET lease=0,retry_at=unixepoch()+? WHERE id=? AND owner=?',delay,row.id,owner).run();
    }
    // Per-chat ordering above and Telegram retry_after provide backpressure without long sleeps.
  }
}
export async function maintenance(env) {
  const store=new Store(env.DB,env.ADMIN_ID);
  await store.notifications();
  await flushOutbox(store,env);
  await store.q('DELETE FROM pending WHERE created<unixepoch()-1800').run();
  await store.q('DELETE FROM updates WHERE done=1 AND created<unixepoch()-604800').run();
  await store.q('DELETE FROM outbox WHERE sent<>0 AND created<unixepoch()-604800').run();
}
export default {
  async fetch(request,env,ctx) {
    const url=new URL(request.url);
    if(url.pathname==='/health' && request.method==='GET') return Response.json({service:'telegram-test-bot',configured:configured(env)}, {status:configured(env)?200:503});
    if(url.pathname!=='/webhook') return new Response('Not found',{status:404});
    if(request.method!=='POST') return new Response('Method not allowed',{status:405});
    if(!configured(env)) return new Response('Not configured',{status:503});
    if(!await equalSecret(request.headers.get('X-Telegram-Bot-Api-Secret-Token')||'',env.WEBHOOK_SECRET)) return new Response('Forbidden',{status:403});
    if(Number(request.headers.get('content-length')||0)>262144) return new Response('Too large',{status:413});
    let update;
    try {
      const text=await request.text();
      if(text.length>262144) return new Response('Too large',{status:413});
      update=JSON.parse(text);
      if(!Number.isSafeInteger(update.update_id)||update.update_id<0) throw new Error();
    } catch {return new Response('Invalid update',{status:400});}
    if(!identity(update)) return new Response('OK');
    const store=new Store(env.DB,env.ADMIN_ID);
    try {
      if(!await processUpdate(update,store)) return new Response('Retry',{status:503});
      ctx.waitUntil((async()=>{
        if(update.callback_query) await telegram(env,'answerCallbackQuery',{callback_query_id:update.callback_query.id}).catch(()=>{});
        await store.notifications();
        await flushOutbox(store,env);
      })().catch(()=>console.error('Background delivery deferred to scheduled retry')));
      return new Response('OK');
    } catch {
      console.error('Update failed; Telegram may retry');
      return new Response('Retry',{status:503});
    }
  },
  async scheduled(_event,env,ctx) {
    if(!configured(env)) return;
    ctx.waitUntil(maintenance(env));
  }
};

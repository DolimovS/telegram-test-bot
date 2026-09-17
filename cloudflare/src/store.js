import {UserError,parseAnswers,messages,render,NAV} from './presentation.js';

export class Store {
  constructor(db,admin) {this.db=db;this.admin=Number(admin);}
  q(sql,...args) {return this.db.prepare(sql).bind(...args);}
  authorize(uid) {if(uid!==this.admin) throw new UserError('Bu amal faqat administrator uchun.');}
  async create(uid,key,delayed,deadline,source) {
    this.authorize(uid);key=parseAnswers(key);
    if(deadline!==null && deadline<=Date.now()/1000) throw new UserError('Muddat kelajakda bo‘lishi kerak.');
    const results=await this.db.batch([
      this.q(`INSERT INTO tests(code,key,delayed,deadline,source_update)
        SELECT code,?,?,?,? FROM available_codes c
        WHERE NOT EXISTS(SELECT 1 FROM tests t WHERE t.code=c.code)
        AND NOT EXISTS(SELECT 1 FROM retired_codes r WHERE r.code=c.code)
        AND NOT EXISTS(SELECT 1 FROM tests WHERE source_update=?)
        ORDER BY code LIMIT 1`,key,delayed,deadline,source,source),
      this.q('DELETE FROM available_codes WHERE code=(SELECT code FROM tests WHERE source_update=?)',source),
      this.q('SELECT code FROM tests WHERE source_update=?',source)
    ]);
    const row=results[2].results[0];
    if(!row) throw new UserError('Barcha 4 xonali test kodlari band. Yangi test yaratib bo‘lmaydi.');
    return row.code;
  }
  async expire() {await this.q('UPDATE tests SET closed=1 WHERE closed=0 AND deadline<=unixepoch()').run();}
  async close(uid,code) {
    this.authorize(uid);
    const row=await this.q('UPDATE tests SET closed=1 WHERE code=? RETURNING code',code).first();
    if(!row) throw new UserError('Test topilmadi.');
  }
  check(test,answers) {
    if(!test) throw new UserError('Test topilmadi.');
    if(test.archived) throw new UserError('Test arxivlangan. Javob qabul qilinmaydi.');
    if(test.closed || (test.deadline!==null && test.deadline<=Date.now()/1000)) throw new UserError('Test yopilgan.');
    if(test.key.length!==answers.length) throw new UserError(`Javoblar soni ${test.key.length} ta bo‘lishi kerak.`);
  }
  async preview(uid,text,source) {
    const match=/^(\S+)\s+([\s\S]+)$/.exec(text.trim());
    if(!match) throw new UserError('Kod va barcha javoblarni bitta xabarda yuboring: 4827 ABCDAB');
    const code=match[1], answers=parseAnswers(match[2]);
    const test=await this.q('SELECT * FROM tests WHERE code=?',code).first();
    this.check(test,answers);
    if(await this.q('SELECT 1 FROM attempts WHERE code=? AND uid=?',code,uid).first()) throw new UserError('Siz bu testni topshirgansiz.');
    const token=crypto.randomUUID().replaceAll('-','');
    await this.q(`INSERT INTO pending(token,uid,code,answers,created,source_update) VALUES(?,?,?,?,unixepoch(),?) ON CONFLICT(source_update) DO NOTHING`,token,uid,code,answers,source).run();
    return this.q('SELECT token,code,answers FROM pending WHERE source_update=? AND uid=?',source,uid).first();
  }
  async confirm(uid,token) {
    const pending=await this.q('SELECT * FROM pending WHERE token=? AND uid=?',token,uid).first();
    if(!pending) throw new UserError('Tasdiqlash muddati tugagan. Javoblarni qayta yuboring.');
    const prior=await this.q('SELECT code FROM attempts WHERE code=? AND uid=?',pending.code,uid).first();
    if(prior) return prior.code;
    const test=await this.q('SELECT * FROM tests WHERE code=?',pending.code).first();
    this.check(test,pending.answers);
    const wrong=Array.from(pending.answers,(a,i)=>a===test.key[i]?null:i+1).filter(x=>x!==null);
    const row=await this.q(`INSERT INTO attempts(code,uid,answers,submitted,score,wrong)
      SELECT p.code,p.uid,p.answers,unixepoch(),?,? FROM pending p JOIN tests t ON t.code=p.code
      WHERE p.token=? AND p.uid=? AND p.created>=unixepoch()-1800 AND t.closed=0 AND t.archived=0
      AND (t.deadline IS NULL OR t.deadline>unixepoch())
      ON CONFLICT(code,uid) DO NOTHING RETURNING code`,test.key.length-wrong.length,JSON.stringify(wrong),token,uid).first();
    if(row) return row.code;
    if(await this.q('SELECT code FROM attempts WHERE code=? AND uid=?',pending.code,uid).first()) return pending.code;
    throw new UserError('Test yopilgan yoki tasdiqlash muddati tugagan.');
  }
  async history(uid,all=false,page=0) {
    if(all) this.authorize(uid);
    const where=all?'':'WHERE a.uid=?',params=all?[]:[uid];
    const result=await this.q(`SELECT a.code,a.uid,a.answers,a.submitted,
      CASE WHEN ?=1 OR t.delayed=0 OR t.closed=1 OR t.deadline<=unixepoch() THEN a.score ELSE NULL END score,
      CASE WHEN ?=1 OR t.delayed=0 OR t.closed=1 OR t.deadline<=unixepoch() THEN a.wrong ELSE NULL END wrong
      FROM attempts a JOIN tests t USING(code) ${where}
      ORDER BY a.submitted DESC,a.code DESC LIMIT 4 OFFSET ?`,Number(all),Number(all),...params,page*3).all();
    return {rows:result.results.slice(0,3),more:result.results.length>3};
  }
  async result(uid,code) {
    return this.q(`SELECT a.code,a.uid,a.answers,a.submitted,
      CASE WHEN t.delayed=0 OR t.closed=1 OR t.deadline<=unixepoch() THEN a.score ELSE NULL END score,
      CASE WHEN t.delayed=0 OR t.closed=1 OR t.deadline<=unixepoch() THEN a.wrong ELSE NULL END wrong
      FROM attempts a JOIN tests t USING(code) WHERE a.uid=? AND a.code=?`,uid,code).first();
  }
  async tests(uid,page=0,archived=false) {
    this.authorize(uid);
    const result=await this.q(`SELECT t.code,t.deadline,t.delayed,t.archived,t.closed OR t.deadline<=unixepoch() AS closed,
      (SELECT COUNT(*) FROM attempts a WHERE a.code=t.code) submissions
      FROM tests t WHERE t.archived=? ORDER BY t.rowid DESC LIMIT 6 OFFSET ?`,Number(archived),page*5).all();
    return {rows:result.results.slice(0,5),more:result.results.length>5};
  }
  async details(uid,code) {
    this.authorize(uid);await this.expire();
    const row=await this.q(`SELECT t.code,t.deadline,t.delayed,t.archived,t.closed OR t.deadline<=unixepoch() AS closed,
      (SELECT COUNT(*) FROM attempts a WHERE a.code=t.code) submissions FROM tests t WHERE t.code=?`,code).first();
    if(!row) throw new UserError('Test topilmadi.');return row;
  }
  async archive(uid,code) {this.authorize(uid);const r=await this.q('UPDATE tests SET archived=1,closed=1 WHERE code=? RETURNING code',code).first();if(!r) throw new UserError('Test topilmadi.');}
  async unarchive(uid,code) {this.authorize(uid);const r=await this.q('UPDATE tests SET archived=0 WHERE code=? RETURNING code',code).first();if(!r) throw new UserError('Test topilmadi.');}
  async deleteEmpty(uid,code) {
    this.authorize(uid);
    const row=await this.details(uid,code);
    if(row.submissions) throw new UserError('Bu testda topshirishlar bor. Tarixni saqlash uchun testni arxivlang.');
    const result=await this.db.batch([
      this.q('INSERT OR IGNORE INTO retired_codes(code) VALUES(?)',code),
      this.q('DELETE FROM pending WHERE code=?',code),
      this.q('DELETE FROM tests WHERE code=? AND NOT EXISTS(SELECT 1 FROM attempts WHERE code=?) RETURNING code',code,code)
    ]);
    if(!result[2].results[0]) throw new UserError('Bu testda topshirishlar bor. Tarixni saqlash uchun testni arxivlang.');
  }
  outboxStatements(id,payloads) {
    return [this.q(`INSERT OR IGNORE INTO outbox(id,uid,payload,created)
      SELECT ? || ':' || printf('%04d',CAST(key AS INTEGER)),json_extract(value,'$.chat_id'),value,unixepoch()
      FROM json_each(?)`,id,JSON.stringify(payloads))];
  }
  async notifications() {
    await this.expire();
    const {results}=await this.q(`SELECT a.* FROM attempts a JOIN tests t USING(code)
      WHERE a.notified=0 AND (t.closed=1 OR t.delayed=0) ORDER BY a.submitted LIMIT 2`).all();
    for(const row of results) {
      await this.db.batch([...this.outboxStatements(`result:${row.code}:${row.uid}`,messages(row.uid,render(row),NAV)),
        this.q('UPDATE attempts SET notified=1 WHERE code=? AND uid=?',row.code,row.uid)]);
    }
  }
}

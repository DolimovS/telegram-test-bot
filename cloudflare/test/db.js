import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
export class TestDB {
  constructor() {
    this.raw=new DatabaseSync(':memory:');
    this.raw.exec(readFileSync(new URL('../migrations/0001_initial.sql',import.meta.url),'utf8'));
  }
  prepare(sql) {
    const db=this;
    const statement={sql,args:[],bind(...args){this.args=args;return this;},
      execute(){const results=db.raw.prepare(sql).all(...this.args);return {success:true,results,meta:{changes:db.raw.prepare('SELECT changes() n').get().n}};},
      async all(){return this.execute();},async run(){return this.execute();},async first(){return this.execute().results[0]||null;}};
    return statement;
  }
  async batch(statements) {
    this.raw.exec('BEGIN');
    try {const result=statements.map(s=>s.execute());this.raw.exec('COMMIT');return result;}
    catch(e){this.raw.exec('ROLLBACK');throw e;}
  }
}

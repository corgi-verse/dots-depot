'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const {webcrypto}=require('node:crypto');
const {TextDecoder}=require('node:util');
const source=fs.readFileSync('apps/web/depot.js','utf8');
function context(fetch, options={}) {
  const ctx=vm.createContext({document:options.document||{body:{dataset:{page:''}}},location:options.location||{search:''},history:options.history,URL,URLSearchParams,TextDecoder,crypto:webcrypto,fetch});
  vm.runInContext(source+';globalThis.api={parseStrict,validateDocument,read,catalog,loadMode,filterCards};',ctx);
  return ctx.api;
}
const schema=kind=>JSON.parse(fs.readFileSync('schemas/'+kind+'.schema.json','utf8'));
const catalog={schema:'dots-depot-catalog/1',mode:'trusted',packages:[]};
test('strict parser rejects duplicate keys, overflow, BOM, depth and trailing bytes',()=>{
  const api=context();
  for(const raw of ['{"a":1,"a":2}','{"n":1e999}','\ufeff{}','[]junk','['.repeat(14)+'0'+']'.repeat(14),'NaN','{"a":1,}']) assert.throws(()=>api.parseStrict(raw));
  assert.equal(api.parseStrict('{"a":[true,null,"quoted\\\"value",2]}').a[3],2);
});
test('closed catalog schema rejects unknown fields and unsupported type',()=>{
  const api=context();api.validateDocument(catalog,schema('catalog'),'catalog');
  assert.throws(()=>api.validateDocument({...catalog,unknown:true},schema('catalog'),'catalog'));
  const e={id:'fixture.example',version:'0.1.0',name:'Fixture',summary:'Synthetic',type:'permission',tree_sha256:'0'.repeat(64),manifest_sha256:'0'.repeat(64),audit_sha256:'0'.repeat(64),archive_sha256:'0'.repeat(64),synthetic:false};
  assert.throws(()=>api.validateDocument({...catalog,packages:[e]},schema('catalog'),'catalog'));
  e.type='tool';e.unknown=true;
  assert.throws(()=>api.validateDocument({...catalog,packages:[e]},schema('catalog'),'catalog'));
});
test('audit semantic tuples and invalid dates fail closed',()=>{
  const api=context();const s=schema('audit');
  const a={schema:'dots-depot-audit/1',package:'fixture.example',version:'0.1.0',source:{repository:'https://github.com/fixture/example',commit:'0'.repeat(40),subtree:'0'.repeat(40),path:'parts/example'},tree_sha256:'0'.repeat(64),manifest_sha256:'0'.repeat(64),permissions:{workspace_read:[],workspace_write:[],network:[],credentials:[],public_publish:false,account_changes:false,paid_services:false},audit:{status:'synthetic',auditor:'Synthetic simulator',reviewed_at:'2026-10-04T00:00:00Z'},verification:{tests_passed:0,static_scan:'pass',report_sha256:'0'.repeat(64),tests_status:'not-run',tests_sha256:'not-run'}};
  api.validateDocument(a,s,'audit');
  for(const v of [{tests_passed:18},{tests_status:'human-reviewed-ci'},{tests_sha256:'0'.repeat(64)}])assert.throws(()=>api.validateDocument({...a,verification:{...a.verification,...v}},s,'audit'));
  assert.throws(()=>api.validateDocument({...a,audit:{...a.audit,reviewed_at:'2026-02-30T00:00:00Z'}},s,'audit'));
});
test('fetch cancels over-limit streaming bodies before accumulation',async()=>{
  let cancelled=false;let released=false;let reads=0;
  const api=context(async()=>({ok:true,headers:{get:()=>null},body:{getReader:()=>({read:async()=>({done:false,value:new Uint8Array(65536+(reads++?1:0))}),cancel:async()=>{cancelled=true;},releaseLock:()=>{released=true;}})}}));
  await assert.rejects(api.read('catalog/index.json'));assert.equal(cancelled,true);assert.equal(released,true);assert.equal(reads,2);
});
test('fetch verifies exact document SHA and rejects BOM',async()=>{
  let raw=new TextEncoder().encode(JSON.stringify(catalog));
  const api=context(async()=>({ok:true,headers:{get:()=>null},body:{getReader:()=>{let sent=false;return{read:async()=>sent?{done:true}:(sent=true,{done:false,value:raw}),releaseLock:()=>{}};}}}));
  const result=await api.read('catalog/index.json');assert.equal(result.value.schema,catalog.schema);
  await assert.rejects(api.read('catalog/index.json','0'.repeat(64)));
  raw=new TextEncoder().encode('\ufeff{}');await assert.rejects(api.read('catalog/index.json'));
});
test('catalog validates trust mode as well as schema',async()=>{
  const raw=new TextEncoder().encode(JSON.stringify({...catalog,mode:'synthetic'}));
  const fetch=async path=>{
    const bytes=path.startsWith('schemas/')?new TextEncoder().encode(JSON.stringify(schema('catalog'))):raw;
    return {ok:true,headers:{get:()=>null},body:{getReader:()=>{
      let sent=false;
      return {read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),releaseLock:()=>{}};
    }}};
  };
  await assert.rejects(context(fetch).catalog());
});

function catalogView(demoAvailable=false, fixtures=[]) {
  const nodes=new Map();
  const element=()=>({hidden:false,value:'',textContent:'',children:[],attributes:{},
    replaceChildren(...items){this.children=items;},append(...items){this.children.push(...items);},
    setAttribute(key,value){this.attributes[key]=value;}});
  const node=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
  node('type').value='all';
  const requests=[];const navigations=[];
  const document={body:{dataset:{page:'',demoAvailable:String(demoAvailable)}},getElementById:node,createElement:element};
  const fetch=async path=>{
    requests.push(path);
    const value=path.startsWith('schemas/')?schema('catalog'):
      {schema:'dots-depot-catalog/1',mode:path.startsWith('demo/')?'synthetic':'trusted',packages:path.startsWith('demo/')?fixtures:[]};
    const bytes=new TextEncoder().encode(JSON.stringify(value));
    return {ok:true,headers:{get:()=>null},body:{getReader:()=>{let sent=false;return{
      read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),releaseLock:()=>{}};}}};
  };
  const api=context(fetch,{document,location:{search:'?mode=demo',href:'http://localhost:8765/?mode=demo'},
    history:{replaceState:(_state,_title,url)=>navigations.push(String(url))}});
  return {api,node,requests,navigations};
}
test('trusted-only view hides unavailable demo routes and makes no demo request',async()=>{
  const view=catalogView();await view.api.loadMode(true);
  assert.equal(view.node('catalog-mode').hidden,true);
  assert.equal(view.node('empty-action').hidden,true);
  assert.equal(view.node('count').textContent,'0 approved releases');
  assert.equal(view.node('empty').hidden,false);
  assert.equal(view.node('error').hidden,true);
  assert.equal(view.node('catalog').children.length,0);
  assert.equal(view.requests.some(path=>path.startsWith('demo/')),false);
  assert.equal(new URL(view.navigations.at(-1)).search,'');
  assert.doesNotMatch(view.node('empty-message').textContent,/Paste Inbox|0001/);
  const html=fs.readFileSync('apps/web/index.html','utf8');
  assert.match(html,/<div id="catalog-mode"[^>]* hidden/);
  assert.match(html,/<button id="empty-action"[^>]* hidden/);
  assert.doesNotMatch(html,/Paste Inbox|0001/);
});
test('built local demo keeps navigation, filtering and return to empty trusted catalog',async()=>{
  const entry={id:'fixture.example',version:'0.1.0',name:'Inert fixture',summary:'Synthetic data only',type:'tool',
    tree_sha256:'0'.repeat(64),manifest_sha256:'0'.repeat(64),audit_sha256:'0'.repeat(64),archive_sha256:'0'.repeat(64),synthetic:true};
  const view=catalogView(true,[entry]);await view.api.loadMode(true);
  assert.equal(view.node('catalog-mode').hidden,false);
  assert.equal(view.node('count').textContent,'1 synthetic fixtures');
  assert.equal(view.node('catalog').children.length,1);
  assert.equal(view.node('empty').hidden,true);
  view.node('search').value='no match';view.api.filterCards();
  assert.equal(view.node('empty').hidden,false);
  assert.equal(view.node('empty-action').hidden,false);
  view.node('empty-action').onclick();
  assert.equal(view.node('search').value,'');assert.equal(view.node('catalog').children.length,1);
  await view.api.loadMode(false);
  assert.equal(view.node('count').textContent,'0 approved releases');
  assert.equal(view.node('empty-action').hidden,false);
  assert.equal(view.node('empty-action').textContent,'Explore synthetic fixtures →');
  assert.equal(view.node('error').hidden,true);
});

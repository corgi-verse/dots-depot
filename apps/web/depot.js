'use strict';
const $ = id => document.getElementById(id);
const page = document.body.dataset.page;
const params = new URLSearchParams(location.search);
let demo = params.get('mode') === 'demo';
let index;
let fingerprint;
let generation = 0;
const ID = /^[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*$/;
const VERSION = /^\d+\.\d+\.\d+$/;
const HASH = /^[0-9a-f]{64}$/;
const assert = condition => { if (!condition) throw new Error('Invalid Depot data'); };
const canonical = value => JSON.stringify(value, (_, item) => item && !Array.isArray(item) && typeof item === 'object' ? Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])) : item);
function parseStrict(raw) {
  let pos=0;
  const whitespace=()=>{while(/[ \t\r\n]/.test(raw[pos]||'!'))pos++;};
  const string=()=>{
    const start=pos++;assert(raw[start]==='"');
    while(pos<raw.length){const c=raw[pos++];if(c==='\\'){pos++;continue;}if(c==='"')return JSON.parse(raw.slice(start,pos));}
    throw new Error('Unterminated string');
  };
  function value(depth=0) {
    assert(depth<=12);whitespace();const c=raw[pos];
    if(c==='{'){
      pos++;whitespace();const result=Object.create(null);const seen=new Set();
      if(raw[pos]==='}'){pos++;return result;}
      for(;;){whitespace();const key=string();assert(!seen.has(key));seen.add(key);whitespace();assert(raw[pos++]===':');result[key]=value(depth+1);whitespace();const end=raw[pos++];if(end==='}')return result;assert(end===',');}
    }
    if(c==='['){pos++;whitespace();const result=[];if(raw[pos]===']'){pos++;return result;}for(;;){result.push(value(depth+1));whitespace();const end=raw[pos++];if(end===']')return result;assert(end===',');}}
    if(c==='"')return string();
    for(const [word,item] of [['true',true],['false',false],['null',null]]){if(raw.startsWith(word,pos)){pos+=word.length;return item;}}
    const number=raw.slice(pos).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);assert(number);pos+=number[0].length;const result=Number(number[0]);assert(Number.isFinite(result));return result;
  }
  const result=value();whitespace();assert(pos===raw.length);return result;
}
function validate(value,schema) {
  if('const' in schema)assert(value===schema.const);
  if('enum' in schema)assert(schema.enum.some(item=>item===value));
  if(schema.type==='object'){
    assert(value&&typeof value==='object'&&!Array.isArray(value));assert(canonical(Object.keys(value).sort())===canonical(Object.keys(schema.properties).sort()));
    for(const [key,spec] of Object.entries(schema.properties))validate(value[key],spec);
  } else if(schema.type==='array'){
    assert(Array.isArray(value)&&value.length<=schema.maxItems);assert(new Set(value.map(canonical)).size===value.length);for(const item of value)validate(item,schema.items);
  } else if(schema.type==='string'){
    assert(typeof value==='string'&&Array.from(value).length>=schema.minLength&&Array.from(value).length<=schema.maxLength&&!/[\u0000-\u001f\u007f]/.test(value));
    if(schema.pattern)assert(new RegExp(schema.pattern).test(value));
    if(schema.format==='date-time'){assert(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value));const time=Date.parse(value);assert(Number.isFinite(time)&&new Date(time).toISOString().replace('.000Z','Z')===value);}
  } else if(schema.type==='integer')assert(Number.isSafeInteger(value)&&value>=schema.minimum&&value<=schema.maximum);
  else if(schema.type==='boolean')assert(typeof value==='boolean');
}
function pathLabel(value){assert(typeof value==='string'&&value.length<=240&&/^[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*$/.test(value));assert(value.split('/').every(p=>p!=='.'&&p!=='..'&&!['.git','.depot'].includes(p.toLowerCase())));}
function validateDocument(value,schema,kind){
  validate(value,schema);
  if(kind==='package'||kind==='audit')pathLabel(value.source.path);
  if(kind==='package'){assert(value.audit==='audits/'+value.id+'/'+value.version+'.json');for(const e of value.executables)pathLabel(e);}
  if(kind==='package'||kind==='audit'){
    const requests=kind==='package'?value.requests:value.permissions;
    for(const field of ['workspace_read','workspace_write'])for(const p of requests[field])pathLabel(p.endsWith('/**')?p.slice(0,-3):p);
  }
  if(kind==='audit'){
    const v=value.verification;assert((v.tests_status==='not-run'&&v.tests_passed===0&&v.tests_sha256==='not-run')||(v.tests_status==='human-reviewed-ci'&&v.tests_passed>0&&HASH.test(v.tests_sha256)));
  }
}
const prefix = () => demo ? 'demo/' : '';
const text = (tag, value, className) => {
  const element = document.createElement(tag);
  element.textContent = String(value);
  if (className) element.className = className;
  return element;
};
const digest = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', value)), x => x.toString(16).padStart(2, '0')).join('');
async function read(path, pin) {
  const response = await fetch(path, {credentials:'omit', redirect:'error', cache:'no-store'});
  assert(response.ok && Number(response.headers.get('content-length') || 0) <= 131072);
  assert(response.body);
  const reader=response.body.getReader();const chunks=[];let total=0;
  try {
    for(;;){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;if(total>131072){await reader.cancel();throw new Error('Depot byte limit');}chunks.push(value);}
  } finally {reader.releaseLock();}
  const raw=new Uint8Array(total);let offset=0;for(const chunk of chunks){raw.set(chunk,offset);offset+=chunk.byteLength;}
  const hash = await digest(raw);
  if (pin) assert(hash === pin);
  const value = parseStrict(new TextDecoder('utf-8', {fatal:true,ignoreBOM:true}).decode(raw));
  return {value, hash};
}
async function catalog() {
  const [result,schema] = await Promise.all([read(prefix() + 'catalog/index.json'),read('schemas/catalog.schema.json')]);
  const value = result.value;
  validateDocument(value,schema.value,'catalog');
  assert(value.schema === 'dots-depot-catalog/1' && value.mode === (demo ? 'synthetic':'trusted'));
  assert(Array.isArray(value.packages) && value.packages.length <= 256);
  const seen = new Set();
  for (const e of value.packages) {
    assert(ID.test(e.id) && VERSION.test(e.version) && e.synthetic === demo);
    for (const field of ['name','summary','type']) assert(typeof e[field] === 'string' && e[field].length <= 320);
    for (const field of ['tree_sha256','manifest_sha256','audit_sha256','archive_sha256']) assert(HASH.test(e[field]));
    const key = e.id + '@' + e.version;
    assert(!seen.has(key)); seen.add(key);
  }
  return {index:value, fingerprint:result.hash};
}
function link(pageName, entry) {
  return pageName + '?id=' + encodeURIComponent(entry.id) + '&version=' + encodeURIComponent(entry.version) + (demo ? '&mode=demo':'');
}
function facts(container, rows) {
  container.replaceChildren();
  for (const [name, value] of rows) {
    const row = document.createElement('div');
    row.append(text('dt', name), text('dd', Array.isArray(value) ? (value.length ? value.join('\n'):'None') : value));
    container.append(row);
  }
}
function requestRows(requests) {
  assert(requests && typeof requests === 'object');
  for (const field of ['workspace_read','workspace_write','network','credentials']) assert(Array.isArray(requests[field]) && requests[field].every(v=>typeof v==='string'));
  for (const field of ['public_publish','account_changes','paid_services']) assert(typeof requests[field]==='boolean');
  return [['Reads',requests.workspace_read],['Writes',requests.workspace_write],['Network',requests.network],['Credentials',requests.credentials],['Publication',requests.public_publish?'Requested':'None'],['Account changes',requests.account_changes?'Requested':'None'],['Paid services',requests.paid_services?'Requested':'None']];
}
function badges(manifest) {
  $('badges').replaceChildren(text('span',demo?'SYNTHETIC — NO HUMAN APPROVAL':'HUMAN AUDITED / EXACT RELEASE','badge'+(demo?' synthetic':'')),text('span','SOURCE PINNED','badge'),text('span','v'+manifest.version,'badge'),text('span',manifest.type.toUpperCase(),'badge'));
}
function filterCards() {
  if (!index) return;
  const query = $('search').value.toLocaleLowerCase();
  const type = $('type').value;
  const entries = index.packages.filter(e=>(type==='all'||e.type===type)&&[e.id,e.name,e.summary,e.type].join(' ').toLocaleLowerCase().includes(query));
  $('catalog').replaceChildren();
  for (const e of entries) {
    const card = text('article','','card');
    const top = text('div','','card-top');
    top.append(text('span',e.type.slice(0,2).toUpperCase(),'part-icon'),text('span',e.type.toUpperCase()+' / v'+e.version));
    const title = text('h3','');const titleLink=text('a',e.name);titleLink.href=link('package.html',e);title.append(titleLink);
    const bottom=text('div','','card-bottom');
    bottom.append(text('span',demo?'SYNTHETIC FIXTURE':'HUMAN AUDITED','tag'+(demo?'':' human')));
    const details=text('a','Inspect release →');details.href=link('package.html',e);bottom.append(details);
    card.append(top,title,text('p',e.summary),bottom);$('catalog').append(card);
  }
  $('count').textContent=entries.length+' '+(demo?'synthetic fixtures':'approved releases');
  $('empty').hidden=entries.length!==0;
  if (!entries.length) {
    const noMatches=index.packages.length>0;
    $('empty-title').textContent=noMatches?'No parts match this search.':'The warehouse is waiting for its first approved release.';
    $('empty-message').textContent=noMatches?'Try another name or choose all package types.':'Real Paste Inbox is reserved for package #0001. Its exact source and release still need human approval.';
    $('empty-action').textContent=noMatches?'Clear search & filters':'Explore synthetic fixtures →';
    $('empty-action').onclick=()=>{ if(noMatches){$('search').value='';$('type').value='all';filterCards();}else loadMode(true); };
  }
}
async function loadMode(useDemo) {
  const token=++generation;
  demo=useDemo;index=undefined;
  $('catalog').replaceChildren();$('empty').hidden=true;$('error').hidden=true;$('catalog').setAttribute('aria-busy','true');
  $('count').textContent='Loading catalog…';
  $('trusted-mode').setAttribute('aria-pressed',String(!demo));$('demo-mode').setAttribute('aria-pressed',String(demo));
  $('mode-note').textContent=demo?'DEMO ONLY — These original fixtures have no human release approval. They demonstrate inert staging and verification.':'Only exact releases with maintainer human approval belong in this catalog.';
  $('mode-note').className='mode-note'+(demo?' demo':'');
  const url=new URL(location.href);demo?url.searchParams.set('mode','demo'):url.searchParams.delete('mode');history.replaceState(null,'',url);
  try {
    const result=await catalog();if(token!==generation)return;
    index=result.index;fingerprint=result.fingerprint;filterCards();
  } catch (_) {if(token===generation){$('error').hidden=false;$('count').textContent='Catalog unavailable';}}
  finally {if(token===generation)$('catalog').setAttribute('aria-busy','false');}
}
async function detail() {
  try {
    const id=params.get('id');const version=params.get('version');
    assert(ID.test(id||'')&&VERSION.test(version||''));
    const result=await catalog();index=result.index;fingerprint=result.fingerprint;
    const entry=index.packages.find(e=>e.id===id&&e.version===version);assert(entry);
    const [mresult,aresult]=await Promise.all([read(prefix()+'packages/'+id+'/'+version+'.json',entry.manifest_sha256),read(prefix()+'audits/'+id+'/'+version+'.json',entry.audit_sha256)]);
    const m=mresult.value;const a=aresult.value;
    const [ms,as]=await Promise.all([read('schemas/package.schema.json'),read('schemas/audit.schema.json')]);
    validateDocument(m,ms.value,'package');validateDocument(a,as.value,'audit');
    assert(m.schema==='dots-depot-package/1'&&a.schema==='dots-depot-audit/1');
    assert(m.id===id&&m.version===version&&a.package===id&&a.version===version);
    for(const field of ['name','summary','type','tree_sha256'])assert(m[field]===entry[field]);
    assert(m.tree_sha256===entry.tree_sha256&&a.tree_sha256===m.tree_sha256&&a.manifest_sha256===entry.manifest_sha256);
    assert(a.audit.status===(demo?'synthetic':'approved')&&a.verification.static_scan==='pass'&&canonical(a.source)===canonical(m.source)&&canonical(a.permissions)===canonical(m.requests));
    assert(/^[0-9a-f]{40}(?:[0-9a-f]{24})?$/.test(m.source.commit)&&/^[0-9a-f]{40}(?:[0-9a-f]{24})?$/.test(m.source.subtree));
    assert(/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(m.source.repository));
    const requests=requestRows(m.requests);
    $('name').textContent=page==='audit'?'Audit / '+m.name:m.name;
    $('summary').textContent=page==='audit'?(demo?'This is a synthetic receipt for a fixture. No person approved this release.':'Human review of this exact release. Approval does not transfer to future versions.'):m.summary;
    document.title=(page==='audit'?'Audit / ':'')+m.name+' — Dots Depot';badges(m);
    $('back').href=page==='audit'?link('package.html',entry):'index.html'+(demo?'?mode=demo':'');
    facts($('requests'),requests);
    const sourceRows=[['Repository',m.source.repository],['Commit',m.source.commit],['Subtree',m.source.subtree],['Source path',m.source.path],['Tree SHA-256',m.tree_sha256],['Manifest SHA-256',entry.manifest_sha256],['Catalog SHA-256',fingerprint]];
    if(page==='package') {
      $('identity').textContent=m.id+' / '+m.type.toUpperCase();
      facts($('compatibility'),[['Dotsys',m.compatibility.dotsys],['Platform',m.compatibility.platform],['Python',m.compatibility.python],['Dependencies',m.dependencies],['Executable source',m.executables],['License',m.license]]);
      facts($('source'),sourceRows);
      $('archive').href=prefix()+'artifacts/'+id+'/'+version+'.tar';
      $('audit-link').href=link('audit.html',entry);
      $('command').value='python3 -m depot --root site'+(demo?'/demo --demo':'')+' \\\n  --catalog-sha256 '+fingerprint+' \\\n  stage '+id+' --version '+version+' \\\n  --destination .depot/staging';
      $('copy').onclick=async()=>{
        try {await navigator.clipboard.writeText($('command').value);$('copy-status').textContent='Command copied. Check the fingerprint independently before staging.';}
        catch(_){$('command').focus();$('command').select();$('copy-status').textContent='Select and copy the command manually.';}
      };
    } else {
      facts($('audit-record'),[['Status',demo?'Synthetic simulation — no approval':'Human audited'],['Auditor',a.audit.auditor],['Reviewed at',a.audit.reviewed_at],['Package tests',a.verification.tests_status==='not-run'?'Not run':String(a.verification.tests_passed)+' passed / human-reviewed CI'],['Static scan',a.verification.static_scan],['Audit SHA-256',entry.audit_sha256]]);
      facts($('source'),sourceRows.concat([['Report SHA-256',a.verification.report_sha256]]));
      $('receipt-download').href=prefix()+'audits/'+id+'/'+version+'.json';
    }
    $('detail').hidden=false;$('status').textContent=demo?'Synthetic fixture loaded. Nothing has been staged.':'Exact release loaded. Nothing has been staged.';
  } catch(_){$('status').textContent='Exact release could not be verified.';$('error').hidden=false;}
}
if(page==='catalog') {
  $('search').addEventListener('input',filterCards);$('type').addEventListener('change',filterCards);
  $('trusted-mode').onclick=()=>loadMode(false);$('demo-mode').onclick=()=>loadMode(true);$('retry').onclick=()=>loadMode(demo);loadMode(demo);
} else if(page==='package'||page==='audit') detail();

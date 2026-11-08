/* Isolated browser regression: no Ray5 connection or firmware writes. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'build', 'grbl-ui-test');
fs.mkdirSync(output, {recursive:true});
const metadata = JSON.parse(execFileSync('python', ['-c', 'import ast,json; from pathlib import Path; tree=ast.parse(Path("app.py").read_text(encoding="utf-8-sig")); print(json.dumps(next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=="GRBL_SETTING_INFO")))'], {cwd:root,encoding:'utf8'}));
const initial = {'0':'3','1':'250','2':'0','3':'0','4':'0','5':'1','6':'0','10':'1','11':'0.010','12':'0.002','13':'0','20':'1','21':'1','22':'1','23':'3','24':'200.000','25':'2000.000','26':'250','27':'2.000','30':'1000','31':'0','32':'1','100':'80.000','101':'80.000','102':'100.000','110':'24000.000','111':'24000.000','112':'1000','120':'500','121':'500','122':'200','130':'400','131':'365','132':'300','150':'-1.000'};
let values = {...initial};
let mode = 'normal';
let posts = [];
let polls = 0;
let remaining = 0;
let holdCollection = false;
let collectFailure = false;
let omitKey = '';
const rows = () => Object.entries(values).filter(([key])=>key!==omitKey).map(([key,value])=>({key,code:'$'+key,value,...(metadata[key]||{description:'Unknown / firmware-specific setting',unit:'raw number',notes:'Firmware-specific setting'})}));
const raw = () => Object.entries(values).map(([key,value])=>`$${key}=${value}`).join('\n')+'\nok';
const identity = {ok:true,firmware_version:'1.3a.20211103',board:'LGT LASER RAY5 V1.1',machine:'Longer Laser Ray5',software:'v1.9.11',working_size:{label:'400 x 365 mm'},raw:'[VER:1.3a.20211103:]\nok'};
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
  if(url.pathname==='/api/machine-settings/collect'){
    assert.equal(req.method,'POST');assert.equal(req.headers['x-ray5-pilot-request'],'1');
    remaining=1;
    return collectFailure?json({ok:false,error:'Controller offline'},502):json({ok:true,started:true},202);
  }
  if(url.pathname==='/api/machine-settings/collect/status'){
    polls++;
    if(holdCollection||remaining-->0)return json({ok:true,running:true});
    if(collectFailure)return json({ok:false,running:false,error:'Read-back offline'},502);
    return json({ok:true,running:false,settings:rows(),raw:raw(),grbl_version:identity});
  }
  if(url.pathname==='/api/machine-settings' && req.method==='POST'){
    assert.equal(req.headers['x-ray5-pilot-request'],'1');
    const chunks=[];for await (const chunk of req)chunks.push(chunk);
    const body=JSON.parse(Buffer.concat(chunks));posts.push(body);
    if(mode==='backup-failed')return json({ok:false,error:'Automatic GRBL backup failed; save was not performed.',backup:{error:'Backup storage unavailable'},results:[]},500);
    if(mode==='transport-failed'){res.destroy();return;}
    const results=body.changes.map(change=>{
      if(mode==='partial'&&change.key==='111')return {key:change.key,ok:false,message:'error: rejected by firmware'};
      if(mode!=='mismatch')values[change.key]=change.value;
      return {key:change.key,ok:true,message:'ok'};
    });
    if(mode==='readback-failed')collectFailure=true;
    return json({ok:results.every(r=>r.ok),results,backup:{file:'backups/grbl/test-backup.txt'}},results.every(r=>r.ok)?200:207);
  }
  if(url.pathname.startsWith('/api/'))return json({ok:false,error:'Unexpected API'},404);
  const file=url.pathname==='/machine-settings'?'web/templates/machine_settings.html':url.pathname.startsWith('/static/')?'web/'+url.pathname.slice(1):null;
  if(!file){res.writeHead(404);res.end();return;}
  const target=path.resolve(root,file);
  if(!target.startsWith(root+path.sep)||!fs.existsSync(target)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.ico':'image/x-icon'})[path.extname(target)]||'application/octet-stream');res.end(fs.readFileSync(target));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM?{executablePath:process.env.PLAYWRIGHT_CHROMIUM}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:950}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const ready=()=>page.waitForFunction(()=>settingsReady&&!busy());
  const search=async code=>{await page.locator('#msSearch').fill(code);};
  const edit=async(key,value)=>{await search('$'+key);await page.locator('#msValue_'+key).fill(value);};
  const review=async()=>{await page.locator('#msSave').click();assert(await page.locator('#msReview').isVisible());};
  const apply=async()=>{await page.locator('#msApply').click();await page.waitForFunction(()=>!saving&&!window.__firmwareCollectRunning);};
  await page.goto(base+'/machine-settings');await ready();
  assert.equal(await page.locator('#msCategories button').count(),6);
  assert.equal(await page.locator('#msVersionCard').getAttribute('open'),null);
  const original=execFileSync('git',['show','HEAD:web/templates/machine_settings.html'],{cwd:root,encoding:'utf8'});
  const ids=await page.locator('[id]').evaluateAll(els=>els.map(el=>el.id));
  assert.equal(ids.length,new Set(ids).size);
  for(const [,id] of original.matchAll(/\bid="([^"]+)"/g))assert(ids.includes(id),'Missing legacy ID '+id);
  await page.screenshot({path:path.join(output,'motion-desktop.png'),fullPage:true});
  // Search includes unknown values and hidden Z-axis rows, without inventing settings.
  await search('$150');assert.equal(await page.locator('#msValue_150').inputValue(),'-1.000');
  await search('$102');assert.equal(await page.locator('#msValue_102').inputValue(),'100.000');
  await search('$31');assert.equal(await page.locator('#msValue_31').inputValue(),'0');
  await edit('110','18000');
  await page.locator('[data-category="homing"]').click();
  await page.getByRole('checkbox',{name:'$23 Homing direction invert: X',exact:true}).uncheck();
  await page.locator('[data-category="laser"]').click();await page.locator('#msValue_32').selectOption('0');
  assert.equal(await page.locator('#msPending').textContent(),'3 pending changes');
  const before=posts.length;await review();assert.equal(posts.length,before,'Review must not write');
  assert((await page.locator('#msReviewList').textContent()).includes('$23=2'));
  await page.screenshot({path:path.join(output,'review-desktop.png'),fullPage:true});
  await page.locator('#msBack').click();
  await search('$110');await page.locator('.grbl-undo').click();
  assert.equal(await page.locator('#msPending').textContent(),'2 pending changes');
  await page.locator('#msReset').click();
  assert.equal(await page.locator('#msPending').textContent(),'No pending changes');
  // Bad input blocks review, including pasted commands and exponent syntax backend rejects.
  for(const value of ['', 'G0 X10', '1e4', '9'.repeat(400)]){
    await edit('110',value);assert(await page.locator('#msSave').isDisabled(), `Invalid value must block review: ${value.length} chars ${value.slice(0,20)}`);
  }
  await page.locator('#msReset').click();
  // Backup download uses the last controller read, never a pending value.
  await edit('110','18000');
  const downloadPromise=page.waitForEvent('download');await page.locator('#msDownload').click();
  const download=await downloadPromise;const text=fs.readFileSync(await download.path(),'utf8');
  assert(text.includes('$110=24000.000'));assert(!text.includes('$110=18000'));
  // Successful apply sends only reviewed changes and requires an awaited fresh read.
  await review();await apply();
  assert.deepEqual(posts.at(-1),{changes:[{key:'110',value:'18000'}]});
  assert.equal(await page.locator('#msPending').textContent(),'No pending changes');
  assert((await page.locator('#msMsg').textContent()).includes('Verified 1 of 1'));
  assert((await page.locator('[data-key="110"]').textContent()).includes('Verified on controller'));
  // Backup failure leaves drafts in review and does not begin a follow-up read.
  mode='backup-failed';await edit('110','17000');await review();const beforePolls=polls;await apply();
  assert.equal(polls,beforePolls);assert((await page.locator('#msMsg').textContent()).includes('Backup storage unavailable'));
  assert.equal(await page.locator('#msPending').textContent(),'1 pending change');
  await page.locator('#msBack').click();await page.locator('#msReset').click();
  // A partial write must retain the failed draft after read-back.
  mode='partial';await edit('110','16000');await edit('111','15000');await review();await apply();
  assert.equal(await page.locator('#msPending').textContent(),'1 pending change');
  await search('$111');assert.equal(await page.locator('#msValue_111').inputValue(),'15000');
  assert((await page.locator('[data-key="111"]').textContent()).includes('Failed: error: rejected'));
  mode='normal';await review();await apply();assert.equal(await page.locator('#msPending').textContent(),'No pending changes');
  // An accepted write that doesn't read back correctly stays pending.
  mode='mismatch';await edit('110','15500');await review();await apply();
  assert.equal(await page.locator('#msPending').textContent(),'1 pending change');
  assert((await page.locator('[data-key="110"]').textContent()).includes('Not verified: controller reports 16000'));
  await page.locator('#msReset').click();
  // A missing setting in read-back must not disappear with its draft.
  mode='normal';await edit('110','14500');await review();omitKey='110';await apply();
  assert.equal(await page.locator('#msValue_110').inputValue(),'14500');
  assert((await page.locator('[data-key="110"]').textContent()).includes('setting missing'));
  omitKey='';await page.locator('#msReset').click();
  // Transport failure is visible and edits remain pending.
  mode='transport-failed';await edit('110','14000');await review();await apply();
  assert((await page.locator('#msMsg').textContent()).includes('Save failed:'));assert.equal(await page.locator('#msPending').textContent(),'1 pending change');
  await page.locator('#msBack').click();await page.locator('#msReset').click();
  // Read-back failure locks Apply until another successful controller read.
  mode='readback-failed';await edit('110','13000');await review();await apply();
  assert((await page.locator('#msMsg').textContent()).includes('not verified'));
  assert(await page.locator('#msSave').isDisabled());assert.equal(await page.locator('#msValue_110').inputValue(),'13000');
  collectFailure=false;mode='normal';page.once('dialog',dialog=>dialog.dismiss());await page.locator('#msRefresh').click();
  assert.equal(await page.locator('#msPending').textContent(),'1 pending change');
  page.once('dialog',dialog=>dialog.accept());await page.locator('#msRefresh').click();await ready();
  assert.equal(await page.locator('#msPending').textContent(),'No pending changes');
  // Read/Apply are mutually exclusive while the collection job is running.
  holdCollection=true;await page.locator('#msRefresh').click();
  await page.waitForFunction(()=>window.__firmwareCollectRunning);
  assert(await page.locator('#msRefresh').isDisabled());assert(await page.locator('#msSave').isDisabled());
  await page.waitForFunction(()=>collectPollTimer !== null);
  await page.evaluate(()=>{collectPollStartedAt=Date.now()-COLLECT_POLL_TIMEOUT_MS-1;});
  await page.waitForFunction(()=>!window.__firmwareCollectRunning);
  assert((await page.locator('#msMsg').textContent()).includes('timed out'));
  assert(await page.locator('#msSave').isDisabled());
  holdCollection=false;await page.locator('#msRefresh').click();await ready();
  await edit('110','12500');await page.locator('#msChangedOnly').check();assert.equal(await page.locator('.grbl-setting-row').count(),1);
  await page.locator('#msReset').click();await page.locator('#msChangedOnly').uncheck();
  for(const width of [1280,768,375,320]){
    await page.setViewportSize({width,height:950});
    for(const category of ['motion','homing','laser','controller','all','diagnostics']){
      await page.locator(`[data-category="${category}"]`).click();
      if(category==='diagnostics')await page.locator('#msDiagnostics details').evaluateAll(els=>els.forEach(el=>el.open=true));
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Page overflow ${width} ${category}`);
      const clipped=await page.locator('#msEditor input:visible,#msEditor select:visible,.grbl-savebar').evaluateAll(els=>els.filter(el=>{const r=el.getBoundingClientRect();return r.right>innerWidth+1||r.left<0;}).map(el=>el.id||el.className));
      assert.deepEqual(clipped,[],`Clipped ${width} ${category}`);
    }
  }
  await page.locator('[data-category="homing"]').click();
  await page.screenshot({path:path.join(output,'homing-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await page.close();
  // Failure on initial load leaves no editable fabricated settings.
  collectFailure=true;const offline=await browser.newPage();await offline.goto(base+'/machine-settings');
  await offline.waitForFunction(()=>document.getElementById('msMsg').textContent.includes('Controller offline'));
  assert(await offline.locator('#msSave').isDisabled());assert(await offline.locator('#msDownload').isDisabled());
  await offline.close();
  console.log(JSON.stringify({passed:true,firmwareSettings:rows().length,categories:6,writeRequests:posts.length,widths:[1280,768,375,320],runtimeErrors:errors,screenshots:output},null,2));
 }finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);process.exitCode=1;server.closeAllConnections();server.close();});

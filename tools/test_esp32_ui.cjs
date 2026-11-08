/* Isolated ESP32 page regression. Never connects to a Ray5 or writes real EEPROM. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'build', 'esp32-ui-test');
fs.mkdirSync(output, {recursive:true});
const oldSecret='fixture-old-password-123';
const newSecret='fixture-replacement-password';
const initial=[
  ['Sta/SSID','Router SSID','S','Workshop',32,1],
  ['Sta/Password','Router password','S',oldSecret,64,0],
  ['Sta/IPMode','Station address mode','B','0',1,0,[{DHCP:'0'},{Static:'1'}]],
  ['Sta/IP','Station IP address','A','192.0.2.20'],
  ['Sta/Gateway','Router address','A','192.0.2.1'],
  ['Sta/Netmask','Subnet mask','A','255.255.255.0'],
  ['AP/SSID','Access point name','S','Ray5',32,1],
  ['AP/Password','Access point password','S','fixture-access-password',64,8],
  ['AP/IP','Access point IP','A','192.0.2.100'],
  ['AP/Channel','AP channel','I','6',11,1],
  ['Radio/Mode','Wi-Fi mode','B','1',2,0,[{Off:'0'},{Station:'1'},{AP:'2'}]],
  ['System/Hostname','Hostname','S','ray5-test',32,1],
  ['Http/Port','HTTP port','I','8848',65535,1],
  ['Http/Enable','HTTP service','B','1',1,0,[{Disabled:'0'},{Enabled:'1'}]],
  ['Telnet/Enable','Telnet service','B','0',1,0,[{Disabled:'0'},{Enabled:'1'}]],
  ['Flame/Threshold','Flame threshold','I','100',4095,0],
  ['Accel/Sensitivity','Motion sensor sensitivity','I','5',10,1],
  ['Custom/Parameter','<img src=x onerror="window.badLabel=true">','S','unusual setting',64,0],
  ['Custom/Pass','Legacy pass alias','S','fixture-legacy-pass',64,0],
].map(([p,label,type,value,size_or_max,min,options=[]],index)=>({index,path:p,label,type,raw_value:value,value,size_or_max,min,options}));
let settings=structuredClone(initial);
let mode='normal', readFailure=false, infoFailure=false, backupFailure=false, listFailure=false;
let omittedPath='', holdSave=false, releaseSave;
let posts=[], calls=[], downloads=0;
let ws={ok:true,websocket_connected:true,last_status_age_seconds:0.1,latest_status:{state:'Idle'},last_raw_status:'<Idle|MPos:0,0|FS:0,0>',page_id:1,reconnect_count:0};
const identity={ok:true,hostname:'ray5-test',fw_version:'3.0',fw_hw:'ESP32',axis:'XY',primary_sd:'SD',http_host:'192.0.2.10',http_port:8848,native_url:'http://192.0.2.10:8848',websocket_port:8849};
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
  let body=null;
  if(req.method==='POST'){
    assert.equal(req.headers['x-ray5-pilot-request'],'1');
    const chunks=[];for await(const chunk of req)chunks.push(chunk);body=JSON.parse(Buffer.concat(chunks));
  }
  if(url.pathname.startsWith('/api/'))calls.push({url:url.pathname,method:req.method,body});
  if(url.pathname==='/api/esp32/info')return infoFailure?json({ok:false,error:'ESP32 HTTP timed out'},503):json(identity);
  if(url.pathname==='/api/status/live')return json(ws);
  if(url.pathname==='/api/esp32/eeprom'){
    if(readFailure)return json({ok:false,error:'EEPROM read unavailable'},503);
    const rows=settings.filter(row=>row.path!==omittedPath);
    return json({ok:true,settings:rows,raw:JSON.stringify({EEPROM:rows.map(row=>({P:row.path,H:row.label,V:row.raw_value}))})});
  }
  if(url.pathname==='/api/esp32/eeprom/backups')return listFailure?json({ok:false,error:'Backup list offline'},503):json({ok:true,backups:[{name:'fixture-backup.json',setting_count:settings.length}]});
  if(url.pathname==='/api/esp32/eeprom/backup')return backupFailure?json({ok:false,error:'Backup disk full'},500):json({ok:true,backup_file:'fixture-backup.json'});
  if(url.pathname==='/api/esp32/eeprom/backups/fixture-backup.json/download'){
    downloads++;res.writeHead(200,{'Content-Type':'application/json','Content-Disposition':'attachment; filename="fixture-backup.json"'});res.end(JSON.stringify({settings:initial.map(row=>({...row,raw_value:/Password/.test(row.path)?'[redacted]':row.raw_value}))}));return;
  }
  if(url.pathname==='/api/esp32/eeprom/backups/fixture-backup.json')return json({ok:true,data:{settings:initial,raw:JSON.stringify({EEPROM:[{P:'Sta/Password',V:oldSecret}]})}});
  if(url.pathname==='/api/esp32/eeprom/compare')return json({ok:true,difference_count:2,differences:[{path:'Sta/Password',current:oldSecret,backup:'fixture-other-secret'},{path:'System/Hostname',current:'ray5-test',backup:'older-host'}]});
  if(url.pathname==='/api/esp32/eeprom/save'){
    posts.push(body);
    if(holdSave)await new Promise(resolve=>releaseSave=resolve);
    if(mode==='backup-failed')return json({ok:false,error:'Automatic backup failed; save was not performed.',backup:{error:'Backup disk unavailable'},results:[]},500);
    if(mode==='transport-failed'){res.destroy();return;}
    const results=body.changes.map(change=>{
      if(mode==='partial'&&change.path==='Accel/Sensitivity')return {path:change.path,ok:false,response:'error: firmware rejected value'};
      const row=settings.find(row=>row.path===change.path);
      if(mode!=='mismatch'){row.raw_value=change.value;row.value=change.value;}
      return {path:change.path,ok:true,response:'ok',command:`[ESP401]P=${change.path} T=${change.type} V=${change.value}`};
    });
    if(mode==='readback-failed')readFailure=true;
    return json({ok:results.every(row=>row.ok),results,failed:results.filter(row=>!row.ok),backup:{file:'fixture-auto.json'}});
  }
  if(url.pathname==='/api/esp32/command'||url.pathname==='/api/esp32/esp-command')return json({ok:true,raw:body.command||body.cmd});
  if(url.pathname.startsWith('/api/'))return json({ok:false,error:'Unexpected API '+url.pathname},404);
  const file=url.pathname==='/esp32'?'web/templates/esp32.html':url.pathname.startsWith('/static/')?'web/'+url.pathname.slice(1):null;
  if(!file){res.writeHead(404);res.end();return;}
  const target=path.resolve(root,file);
  if(!target.startsWith(root+path.sep)||!fs.existsSync(target)){res.writeHead(404);res.end();return;}
  let content=fs.readFileSync(target);
  if(file.endsWith('.html'))content=content.toString().replace(/\{\{[^\n]+\}\}/g,JSON.stringify({native_url:identity.native_url}));
  res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.ico':'image/x-icon'})[path.extname(target)]||'application/octet-stream');res.end(content);
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM?{executablePath:process.env.PLAYWRIGHT_CHROMIUM}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:950}}), errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{window.open=(...args)=>{window.openedNative=args;};});
    const settled=()=>page.waitForFunction(()=>!espBusy);
    const category=async section=>{await page.locator(`[data-section="${section}"]`).click();};
    const field=p=>page.locator('.esp-field-wrap').filter({has:page.locator(`[id="espValue_${encodeURIComponent(p)}"]`)});
    const input=p=>page.locator(`[id="espValue_${encodeURIComponent(p)}"]`);
    const edit=async(p,value)=>{await category('advanced');await page.locator('#eepromFilter').fill(p);await input(p).fill(value);};
    const review=async()=>{await page.locator('#saveChanges').click();assert(await page.locator('#espReview').isVisible());};
    const apply=async()=>{
      if(await page.locator('#espBackupAckWrap').isVisible())await page.locator('#espBackupAck').check();
      if(await page.locator('#espNetworkAckWrap').isVisible())await page.locator('#espNetworkAck').check();
      await page.locator('#espApply').click();await settled();
    };
    const discard=async()=>{await page.locator('#discardChanges').click();};
    const noSecrets=async()=>{
      const text=await page.locator('body').textContent();
      for(const value of [oldSecret,newSecret,'fixture-access-password','fixture-other-secret','fixture-legacy-pass'])assert(!text.includes(value),'Secret exposed in rendered text');
      assert.equal(await page.evaluate(()=>!!window.badLabel),false,'Firmware label executed HTML');
    };
    await page.goto(base+'/esp32');await page.waitForFunction(()=>eepromReady&&!espBusy);
    assert.equal(await page.locator('#espCategories button').count(),6);
    const original=execFileSync('git',['show','HEAD:web/templates/esp32.html'],{cwd:root,encoding:'utf8'});
    const ids=await page.locator('[id]').evaluateAll(els=>els.map(el=>el.id));
    for(const [,id] of original.matchAll(/\bid="([^"]+)"/g))assert(ids.includes(id),'Missing existing ID '+id);
    assert.equal(calls.filter(call=>call.method==='POST').length,0,'Page load must be read-only');
    assert((await page.locator('#espHealth').textContent()).includes('Idle'));
    await page.screenshot({path:path.join(output,'overview-desktop.png'),fullPage:true});
    await page.locator('#openNative').click();assert.deepEqual(await page.evaluate(()=>window.openedNative),[identity.native_url+'/', '_blank','noopener,noreferrer']);
    await page.evaluate(()=>{deviceInfo.native_url='javascript:alert(1)';window.openedNative=null;openNative();});assert.equal(await page.evaluate(()=>window.openedNative),null);
    await page.evaluate(url=>{deviceInfo.native_url=url;},identity.native_url);
    // Firmware-driven options, bounds and DHCP dependencies; never invent missing settings.
    await category('network');assert(await input('Sta/IP').isDisabled());
    assert.equal(await input('Sta/IPMode').locator('option').count(),2);
    assert.equal(await input('Sta/Password').count(),0,'Stored password must not be placed in an input');
    await input('Sta/IPMode').selectOption('1');assert(await input('Sta/IP').isEnabled());
    await input('Sta/IP').fill('300.0.0.1');assert(await page.locator('#saveChanges').isDisabled());
    await input('Sta/IP').fill('192.0.2.21');await input('Sta/SSID').fill('Changed network');
    await category('services');await input('System/Hostname').fill('pending-host');
    await category('network');assert.equal(await input('Sta/SSID').inputValue(),'Changed network');
    // Secret editing is explicit and remains masked through review, comparison and logs.
    await page.getByRole('checkbox',{name:'Change Router password',exact:true}).check();
    await input('Sta/Password').fill(newSecret);assert.equal(await input('Sta/Password').getAttribute('type'),'password');
    await category('services');await category('network');assert.equal(await input('Sta/Password').inputValue(),newSecret);
    const countBeforeReview=posts.length;await review();assert.equal(posts.length,countBeforeReview);
    assert(await page.locator('#espApply').isDisabled());
    assert(!(await page.locator('#espReviewList').textContent()).includes(newSecret));
    await page.locator('#espNetworkAck').check();assert(await page.locator('#espApply').isDisabled());
    await page.locator('#espBackupAck').check();assert(await page.locator('#espApply').isEnabled());
    await page.screenshot({path:path.join(output,'review-desktop.png'),fullPage:true});
    await page.locator('#espBack').click();await review();assert.equal(await page.locator('#espNetworkAck').isChecked(),false);
    await page.locator('#espBack').click();await discard();
    for(const [p,value] of [['Http/Port','0'],['Http/Port','65536'],['Http/Port','G0 X10'],['Http/Port','1e3'],['System/Hostname',''],['System/Hostname','x'.repeat(33)],['AP/IP','bad-IP']]){
      await edit(p,value);assert(await page.locator('#saveChanges').isDisabled(),`Invalid input accepted ${p} ${value}`);await discard();
    }
    // Undo, duplicate IDs across editor panels, and a literal firmware label.
    await edit('System/Hostname','undo-host');await field('System/Hostname').locator('.esp-undo').click();
    assert.equal(await page.locator('#changedBadge').textContent(),'No pending changes');
    await category('advanced');await page.locator('#eepromFilter').fill('');await noSecrets();
    for(const section of ['network','services','hardware','advanced']){
      await category(section);
      const mounted=await page.locator('[id]').evaluateAll(els=>els.map(el=>el.id));assert.equal(mounted.length,new Set(mounted).size,'Duplicate field IDs after navigation');
    }
    // Backups are read-only and secret-safe; failed creation is not reported as a download.
    await category('backups');await page.locator('#loadBackup').click();await settled();await noSecrets();
    await page.locator('#compareBackup').click();await settled();await noSecrets();
    assert.equal(await page.locator('.esp-comparison-row').count(),1);
    assert((await page.locator('#backupDiff').textContent()).includes('older-host'));
    backupFailure=true;await page.locator('#backupEeprom').click();await settled();assert((await page.locator('#msg').textContent()).includes('Backup disk full'));assert.equal(downloads,0);
    backupFailure=false;const downloadPromise=page.waitForEvent('download');await page.locator('#backupEeprom').click();await downloadPromise;await settled();assert.equal(downloads,1);
    listFailure=true;await page.evaluate(()=>withBusy(loadBackups));await settled();assert(await page.locator('#compareBackup').isDisabled());listFailure=false;await page.evaluate(()=>withBusy(loadBackups));
    // Read-back verification, partial save and secret success.
    await edit('System/Hostname','verified-host');await review();await apply();
    assert.deepEqual(posts.at(-1),{changes:[{path:'System/Hostname',type:'S',value:'verified-host'}],backup_required:false,allow_network_changes:false});
    assert.equal(await page.locator('#changedBadge').textContent(),'No pending changes');assert((await field('System/Hostname').textContent()).includes('Verified on device'));
    mode='partial';await edit('Flame/Threshold','150');await edit('Accel/Sensitivity','7');await category('network');
    await page.getByRole('checkbox',{name:'Change Router password',exact:true}).check();await input('Sta/Password').fill(newSecret);
    await review();await apply();
    assert.equal(posts.at(-1).allow_network_changes,true);
    assert.equal(await page.locator('#changedBadge').textContent(),'1 pending change');
    assert((await page.locator('#saveSummary').textContent()).includes('1 verified, 1 secret changes accepted, 1 failed'));
    await noSecrets();await category('hardware');assert.equal(await input('Accel/Sensitivity').inputValue(),'7');assert((await field('Accel/Sensitivity').textContent()).includes('firmware rejected'));
    mode='normal';await review();await apply();assert.equal(await page.locator('#changedBadge').textContent(),'No pending changes');
    // No optimistic success on mismatch, missing row, backup failure or transport failure.
    mode='mismatch';await edit('System/Hostname','mismatch-host');await review();await apply();assert.equal(await page.locator('#changedBadge').textContent(),'1 pending change');assert((await field('System/Hostname').textContent()).includes('Not verified'));await discard();
    mode='normal';await edit('System/Hostname','missing-host');await review();omittedPath='System/Hostname';await apply();assert.equal(await input('System/Hostname').inputValue(),'missing-host');assert((await field('System/Hostname').textContent()).includes('setting missing'));omittedPath='';await discard();
    mode='backup-failed';await edit('System/Hostname','blocked-host');await review();const readsBefore=calls.filter(c=>c.url==='/api/esp32/eeprom').length;await apply();
    assert((await page.locator('#msg').textContent()).includes('Backup disk unavailable'));assert.equal(calls.filter(c=>c.url==='/api/esp32/eeprom').length,readsBefore);assert.equal(await page.locator('#changedBadge').textContent(),'1 pending change');await page.locator('#espBack').click();await discard();
    mode='transport-failed';await edit('System/Hostname','transport-host');await review();await apply();assert((await page.locator('#msg').textContent()).includes('Request failed'));assert.equal(await page.locator('#changedBadge').textContent(),'1 pending change');await page.locator('#espBack').click();await discard();
    mode='readback-failed';await edit('System/Hostname','offline-host');await review();await apply();
    assert(await page.locator('#saveChanges').isDisabled());assert.equal(await input('System/Hostname').inputValue(),'offline-host');assert((await page.locator('#msg').textContent()).includes('Read-back unavailable'));
    readFailure=false;mode='normal';page.once('dialog',dialog=>dialog.dismiss());await page.locator('#refreshAll').click();assert.equal(await page.locator('#changedBadge').textContent(),'1 pending change');
    page.once('dialog',dialog=>dialog.accept());await page.locator('#refreshAll').click();await settled();assert.equal(await page.locator('#changedBadge').textContent(),'No pending changes');
    // Guard double submissions and prevent concurrent edits during Apply.
    await edit('System/Hostname','single-save-host');await review();holdSave=true;const beforeHold=posts.length;
    await page.locator('#espApply').click();await page.waitForFunction(()=>espBusy);
    assert(await page.locator('#espApply').isDisabled());assert(await page.locator('#refreshAll').isDisabled());assert(await page.locator('[data-section="network"]').isDisabled());
    await page.evaluate(()=>saveChanges());assert.equal(posts.length,beforeHold+1);holdSave=false;releaseSave();await settled();
    // Status explicitly distinguishes HTTP / WebSocket and stale mainboard reports.
    await category('overview');ws.last_status_age_seconds=30;await page.evaluate(()=>withBusy(loadWsStatus));assert(!(await page.locator('#espHealth').textContent()).includes('Idle'));assert((await page.locator('#espHealth').textContent()).includes('Unknown'));
    ws.last_status_age_seconds=null;await page.evaluate(()=>withBusy(loadWsStatus));assert((await page.locator('#espHealth').textContent()).includes('Unknown'));
    ws.last_status_age_seconds=4.8;await page.evaluate(()=>withBusy(loadWsStatus));await page.waitForFunction(()=>document.getElementById('espHealth').textContent.includes('Unknown'));
    infoFailure=true;ws.websocket_connected=false;await page.evaluate(()=>withBusy(async()=>{await loadInfo();await loadWsStatus();}));assert((await page.locator('#espHealth').textContent()).includes('Unavailable'));infoFailure=false;
    await page.evaluate(()=>withBusy(loadInfo));
    // Manual commands require explicit enable and confirmation (except status query).
    await category('advanced');assert(await page.locator('#sendGcode').isDisabled());await page.locator('#espCommandsEnabled').check();await page.locator('#gcodeCmd').fill('?');await page.locator('#sendGcode').click();await settled();
    assert.deepEqual(calls.at(-1),{url:'/api/esp32/command',method:'POST',body:{command:'?'}});
    const beforeManual=calls.length;await page.locator('#gcodeCmd').fill('G0 X1');page.once('dialog',dialog=>dialog.dismiss());await page.locator('#sendGcode').click();assert.equal(calls.length,beforeManual);
    await page.locator('#espCmd').fill('[ESP401]P=Sta/Password T=S V=fixture-manual-secret');page.once('dialog',dialog=>dialog.accept());await page.locator('#sendEsp').click();await settled();
    assert.equal(await page.locator('#espCmd').inputValue(),'');assert(!(await page.locator('body').textContent()).includes('fixture-manual-secret'));await noSecrets();
    await page.locator('#espCommandsEnabled').uncheck();
    // All sections at desktop/tablet/phone sizes, with diagnostics expanded.
    await page.locator('#eepromFilter').fill('');
    for(const width of [1280,768,375,320]){
      await page.setViewportSize({width,height:950});
      for(const section of ['overview','network','services','hardware','backups','advanced']){
        await category(section);
        if(['advanced','backups'].includes(section))await page.locator(`[data-panel="${section}"] details`).evaluateAll(els=>els.forEach(el=>el.open=true));
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Page overflow ${width} ${section}`);
        const clipped=await page.locator('input:visible,select:visible,button:visible,.esp-savebar').evaluateAll(els=>els.filter(el=>{const r=el.getBoundingClientRect();return r.right>innerWidth+1||r.left<0;}).map(el=>el.id||el.className));
        assert.deepEqual(clipped,[],`Clipped controls ${width} ${section}`);
      }
    }
    await category('network');await page.screenshot({path:path.join(output,'network-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1280,height:950});await page.screenshot({path:path.join(output,'network-desktop.png'),fullPage:true});
    await category('backups');await page.screenshot({path:path.join(output,'backups-desktop.png'),fullPage:true});
    assert.deepEqual(errors,[],'Browser runtime errors');await page.close();
    readFailure=true;infoFailure=true;const offline=await browser.newPage();await offline.goto(base+'/esp32');await offline.waitForFunction(()=>!espBusy&&document.getElementById('msg').textContent.includes('EEPROM read unavailable'));
    assert(await offline.locator('#saveChanges').isDisabled());assert.equal(await offline.locator('.esp-value').count(),0);assert((await offline.locator('#espHealth').textContent()).includes('Unknown'));await offline.close();
    console.log(JSON.stringify({passed:true,categories:6,firmwareSettings:settings.length,writeRequests:posts.length,widths:[1280,768,375,320],runtimeErrors:errors,screenshots:output},null,2));
  }finally{if(releaseSave)releaseSave();await browser.close();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);process.exitCode=1;server.closeAllConnections();server.close();});

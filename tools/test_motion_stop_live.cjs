/* Explicitly authorized hardware test: tiny laser-OFF moves, Stop, and recovery Home. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
if(process.env.RAY5_LIVE_MOTION_TEST !== '1' || process.env.RAY5_LIVE_RECOVERY !== '1')
  throw new Error('Requires explicit authorization: RAY5_LIVE_MOTION_TEST=1 and RAY5_LIVE_RECOVERY=1');
const base='http://127.0.0.1:5050';
const resumeFile=process.env.RAY5_LIVE_RESUME_FILE || '';
const verifyOnly=process.env.RAY5_LIVE_VERIFY_ONLY === '1';
assert(!resumeFile || /^ms[a-z0-9]{6}\.gc$/i.test(resumeFile));
const filename=resumeFile || 'ms'+Date.now().toString(36).slice(-6)+'.gc';
const output=path.resolve(__dirname,'../build/motion-stop-live');
fs.mkdirSync(output,{recursive:true});
const report=resumeFile ? JSON.parse(fs.readFileSync(path.join(output,'report.json'),'utf8')) :
  {passed:false,filename,started:new Date().toISOString(),steps:[],statusSamples:[],errors:[],blocked:[]};
assert.equal(report.filename,filename);
if(resumeFile){report.previousFailure=report.failure;delete report.failure;report.resumed=new Date().toISOString();}
let machineFilename=filename, imported=!!resumeFile, uploaded=!!resumeFile;
const headers={'X-Ray5-Pilot-Request':'1'};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(url,method='GET',body){
  const response=await fetch(base+url,{method,headers:body?{...headers,'Content-Type':'application/json'}:headers,
    body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(45000)});
  const data=await response.json();
  if(method!=='GET')report.steps.push({route:url,http:response.status,ok:!!data.ok,message:data.message||data.error||''});
  assert(response.ok&&data.ok,`${url}: ${data.error||data.message||response.status}`);
  return data;
}
async function status(){
  const data=await api('/api/status/live');
  assert(data.websocket_connected&&data.last_status_age_seconds<5,'Fresh live machine status required');
  const raw=data.last_raw_status||'';
  const pos=raw.match(/MPos:([+-]?[\d.]+),([+-]?[\d.]+)/);
  const spindle=raw.match(/FS:[^,|>]+,([+-]?[\d.]+)/);
  assert(pos&&spindle,'Expected actual MPos and FS');
  assert.equal(Number(spindle[1]),0,'Laser spindle value must remain zero');
  const value={state:raw.slice(1).split('|')[0],x:Number(pos[1]),y:Number(pos[2]),raw,
    receivedAt:Date.now()-data.last_status_age_seconds*1000};
  if(!report.statusSamples.length||report.statusSamples.at(-1).raw!==raw)report.statusSamples.push(value);
  return value;
}
async function waitStatus(predicate,timeout=30000){
  const deadline=Date.now()+timeout;
  do{const value=await status();if(predicate(value))return value;await sleep(250);}while(Date.now()<deadline);
  throw new Error('Timed out waiting for expected live machine state');
}
const at=(s,x,y)=>Math.abs(s.x-x)<0.15&&Math.abs(s.y-y)<0.15;
async function firmware(){
  let grbl;
  for(let attempt=0;attempt<3;attempt++){
    await api('/api/machine-settings/collect','POST',{});
    for(let i=0;i<100;i++){
      grbl=await api('/api/machine-settings/collect/status');
      if(!grbl.running)break;
      await sleep(200);
    }
    if(!grbl.running&&grbl.settings?.length >= (report.firmwareBefore?.grblCount||20))break;
    (report.incompleteFirmwareReads ||= []).push({count:grbl.settings?.length||0,running:grbl.running});
    await sleep(1000);
  }
  assert(!grbl.running&&grbl.settings?.length >= (report.firmwareBefore?.grblCount||20));
  const esp=await api('/api/esp32/eeprom');
  assert(esp.settings?.length>0);
  const rows=items=>items.map(item=>[item.path||item.key,String(item.raw_value??item.value??'')]).sort((a,b)=>a[0].localeCompare(b[0]));
  const digest=items=>crypto.createHash('sha256').update(JSON.stringify(rows(items))).digest('hex');
  return {grblCount:grbl.settings.length,espCount:esp.settings.length,grbl:digest(grbl.settings),esp:digest(esp.settings)};
}
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM?{executablePath:process.env.PLAYWRIGHT_CHROMIUM}:{})});
 const page=await browser.newPage({viewport:{width:1280,height:1000}});
 page.on('pageerror',error=>report.errors.push(error.message));
 page.on('dialog',dialog=>/^Stop current job\?|Unlock\/Clear Alarm|Cancel alarm|Upload and run /i.test(dialog.message())?dialog.accept():dialog.dismiss());
 await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),method=req.method();
   if(url.origin!==base)return route.abort('blockedbyclient');
   // This headless page does not open another camera connection or change camera settings.
   if(method==='GET'&&url.pathname==='/api/status'){
     const response=await route.fetch();const data=await response.json();
     return route.fulfill({response,json:{...data,camera_video_enabled:false}});
   }
   if(method==='GET')return route.continue();
   const body=req.postDataJSON();
   let allowed=false;
   if(['/api/stop','/api/unlock','/api/home'].includes(url.pathname))allowed=true;
   if(url.pathname==='/api/move')allowed=body&&['x','y'].includes(body.axis)&&Math.abs(body.distance)<=1&&body.feedrate<=500;
   if(['/api/jobs/frame','/api/jobs/start'].includes(url.pathname))allowed=body?.filename===filename;
   if(!allowed){report.blocked.push({path:url.pathname,method});return route.abort('blockedbyclient');}
   if(url.pathname==='/api/jobs/frame')return route.continue({postData:JSON.stringify({...body,margin:0,feed:60})});
   return route.continue();
 });
 async function click(selector,routeName){
   const responsePromise=page.waitForResponse(response=>new URL(response.url()).pathname===routeName&&response.request().method()==='POST');
   await (typeof selector==='string'?page.locator(selector):selector).click();
   const response=await responsePromise,data=await response.json();
   report.steps.push({route:routeName,http:response.status(),ok:!!data.ok,message:data.message||data.error||''});
   assert(response.ok()&&data.ok,`${routeName}: ${data.error||data.message||response.status()}`);
   await page.waitForFunction(()=>!manualBusy,null,{timeout:45000});
   return data;
 }
 async function recover(label){
   const s=await status();
   if(/^Alarm/i.test(s.state)){
     await click('#unlock','/api/unlock');
     await waitStatus(s=>/^Idle$/.test(s.state));
   }
   const homeStarted=Date.now();
   await click('#homeAll','/api/home');
   await waitStatus(s=>s.receivedAt>=homeStarted-50&&s.state==='Home',15000);
   const ready=await waitStatus(s=>s.receivedAt>=homeStarted&&s.state==='Idle'&&at(s,0,0),60000);
   report[label]=ready;
 }
 try{
   const initial=await status();assert(initial.state==='Idle'&&at(initial,0,0),'Start homed at X0/Y0');
   if(verifyOnly){
     assert(resumeFile&&report.jobStopped&&report.afterJobRecovery&&report.remainingTestFiles.local===null&&report.remainingTestFiles.sd===null);
     imported=false;uploaded=false;
     report.firmwareAfter=await firmware();
     assert.deepEqual(report.firmwareAfter,report.firmwareBefore);
     report.firmwareUnchanged=true;report.final=await status();
     assert(report.final.state==='Idle'&&at(report.final,0,0));
     assert.deepEqual(report.errors,[]);assert.deepEqual(report.blocked,[]);
     report.passed=true;
     return;
   }
   if(!resumeFile)report.firmwareBefore=await firmware();
   else assert.deepEqual(await firmware(),report.firmwareBefore);
   await page.goto(base+'/');
   await page.waitForFunction(()=>document.body.classList.contains('dashboard-ready')&&manualCfg.preset_enabled);
   if(!resumeFile){
   await page.locator('#jogStep').selectOption('1');await page.locator('#jogFeed').selectOption('500');
   report.jogs=[];
   for(const [selector,x,y] of [['#xPlus',1,0],['#yPlus',1,1],['#yMinus',1,0],['#xMinus',0,0]]){
     const started=Date.now();await click(selector,'/api/move');
     const reached=await waitStatus(s=>s.receivedAt>=started-50&&s.state==='Idle'&&at(s,x,y));
     report.jogs.push({control:selector,status:reached.raw});
   }
   const lines=['; Supervised laser-OFF motion/Stop test','; Bounds: X0 Y0 to X2 Y2','M5','G21','G90','G1 X0 Y0 F60 S0'];
   for(let i=0;i<3;i++)lines.push('G1 X2 Y0 F60 S0','G1 X2 Y2 F60 S0','G1 X0 Y2 F60 S0','G1 X0 Y0 F60 S0');
   lines.push('M5','M2');
   assert(!lines.some(line=>/^M[34](?:\s|$)/i.test(line)));
   const form=new FormData();form.append('file',new Blob([lines.join('\n')+'\n'],{type:'text/plain'}),filename);
   const response=await fetch(base+'/api/jobs/import',{method:'POST',headers,body:form});const importedData=await response.json();
   assert(response.ok&&importedData.ok);imported=true;
   await page.evaluate(()=>refreshJobs());
   const row=page.locator('#jobsBody tr').filter({hasText:filename});assert.equal(await row.count(),1);
   const frame=row.getByRole('button',{name:'Frame',exact:true});
   let frameResponsePromise=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/jobs/frame');
   await frame.click();let frameResponse=await frameResponsePromise;let frameData=await frameResponse.json();
   assert(frameResponse.ok()&&frameData.ok);assert(frameData.commands.every(line=>!/^M[34](?:\s|$)/i.test(line)));
   await waitStatus(s=>s.state==='Run'||!at(s,0,0),12000);
   report.completedFrame=await waitStatus(s=>s.state==='Idle'&&at(s,0,0),20000);
   // Interrupt a second frame while its HTTP command batch is still pending.
   const frameRequest=page.waitForRequest(r=>new URL(r.url()).pathname==='/api/jobs/frame');
   frameResponsePromise=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/jobs/frame');
   await frame.click();await frameRequest;await sleep(90);
   assert(await page.locator('#stop').isEnabled());
   await click('#stop','/api/stop');
   frameResponse=await frameResponsePromise;frameData=await frameResponse.json();
   report.interruptedFrame={http:frameResponse.status(),ok:frameData.ok,error:frameData.error,results:frameData.results};
   assert(!frameData.ok,'Interrupted pending frame should report failure, not success');
   report.frameStop=await waitStatus(s=>['Idle','Alarm'].includes(s.state));
   await sleep(1500);const stable=await status();
   assert(['Idle','Alarm'].includes(stable.state));
   await recover('afterFrameRecovery');
   }
   await page.evaluate(()=>refreshJobs());
   const jobRow=page.locator('#jobsBody tr').filter({hasText:filename});
   const localText=fs.readFileSync(path.resolve(__dirname,'../imported_jobs',filename),'utf8');
   assert(!/^\s*M[34](?=\s|S|$)/im.test(localText));
   assert(localText.includes('; Supervised laser-OFF motion/Stop test'));
   await waitStatus(s=>s.state==='Idle'&&at(s,0,0));
   await sleep(1500);
   const startData=await click(jobRow.getByRole('button',{name:'Upload + Run',exact:true}),'/api/jobs/start');
   uploaded=true;
   machineFilename=startData.run_filename||filename;
   assert(/^ms[a-z0-9]{6}\.gc$/i.test(machineFilename),'Only our own temporary SD filename is allowed');
   report.jobStart={ok:startData.ok,upload_ok:startData.upload_ok,run_filename:machineFilename};
   report.jobRun=await waitStatus(s=>s.state==='Run',15000);
   await sleep(1200);
   const stopStarted=Date.now();
   await click('#stop','/api/stop');
   report.jobStopped=await waitStatus(s=>s.receivedAt>=stopStarted-50&&['Idle','Alarm'].includes(s.state));
   await sleep(1500);
   assert(['Idle','Alarm'].includes((await status()).state),'Machine must remain stopped');
   await recover('afterJobRecovery');
   await api('/api/files/delete','POST',{filename:machineFilename,path:'/'});uploaded=false;
   await api('/api/jobs/'+encodeURIComponent(filename),'DELETE');imported=false;
   report.firmwareAfter=await firmware();
   assert.deepEqual(report.firmwareAfter,report.firmwareBefore,'Firmware settings must remain identical');
   report.firmwareUnchanged=true;
   report.final=await status();
   assert(report.final.state==='Idle'&&at(report.final,0,0));
   assert.deepEqual(report.errors,[]);
   assert.deepEqual(report.blocked,[]);
   report.passed=true;
 }catch(error){report.failure=error.message;process.exitCode=1;}
 finally{
   if(!report.passed){
     try{
       const current=await status();
       if(/^(Run|Jog|Hold)/.test(current.state))await api('/api/stop','POST',{});
       report.failureFinal=await status();
     }catch(error){report.safetyCheckError=error.message;}
   }
   report.remainingTestFiles={local:imported?filename:null,sd:uploaded?machineFilename:null};
   report.finished=new Date().toISOString();
   fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
   console.log(JSON.stringify(report,null,2));
   await browser.close();
 }
})();

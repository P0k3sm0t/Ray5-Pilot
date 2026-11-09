/* Real dashboard scripts with isolated HTTP fixtures. Never contacts a Ray5. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),output=path.join(root,'build','dashboard-ui-test');
fs.mkdirSync(output,{recursive:true});
const config=JSON.parse(fs.readFileSync(path.join(root,'config.example.json'),'utf8').replace(/^\uFEFF/,''));
config.manual_controls.default_feedrate=1000;
config.safety.test_fire_enabled=true;config.safety.confirm_dangerous_actions=true;
config.sd_files.auto_refresh_seconds=0;
let commands=[],unexpected=[],failRoute='',holdRoute='',releaseHold;
let emptyJobs=false;
let sdFrameUnavailable=false;
let holdTimelapseList=false,releaseTimelapseList;
let machineState='Idle',online=true,lockout=false,videoEnabled=true,cameraConfigured=true;
let timelapseState={enabled:true,active:false,armed:false};
let consoleItems=[{ts:'10:42:01',level:'info',message:'Fixture connected'}];
const jobs=[{name:'fixture_grid.gc',size_bytes:34500,modified:1794120000,bounds:{min_x:20,max_x:280,min_y:20,max_y:280}},{name:'fixture_coasters.gcode',size_bytes:189000,modified:1794119400,bounds:{min_x:45,max_x:265,min_y:30,max_y:270}}];
const sdFiles=[{name:'LightBurn_001.gc',path:'/LightBurn_001.gc',type:'gcode',size:'34 KB',modified:'-',can_start:true,can_delete:true},{name:'fixture_grid.nc',path:'/fixture_grid.nc',type:'gcode',size:'9 KB',modified:'-',can_start:true,can_delete:true}];
const timelapses=[{name:'fixture_run.mp4',url:'/test/video.mp4',size_bytes:8400000,modified:1794119400},{name:'fixture_second.mp4',url:'/test/second.mp4',size_bytes:1300000,modified:1794119300}];
const image='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600"><rect width="800" height="600" fill="#131e29"/><path d="M60 60H740V540H60Z" fill="#263645" stroke="#597286" stroke-width="12"/><rect x="230" y="150" width="340" height="300" fill="#b59b75"/><text x="400" y="310" text-anchor="middle" fill="#282520" font-size="26">TEST CAMERA</text></svg>';
function status(){return {ok:true,online,state:machineState,state_base:machineState,display_state:machineState,status_source:online?'live_websocket':'fallback_offline',connection_status:online?'Online':'Offline',websocket_page_id:1,machine_position:{x:10,y:20},work_position:{x:10,y:20},work_offset:{x:0,y:0},wco_available:true,feed:0,laser_state_label:'Off',laser_power_label:'S0',air_pump_state:'off',air_pump_label:'Off',job_status:'Idle',job_progress_percent:null,job_file:'',job_time_seconds:null,camera_configured:cameraConfigured,camera_video_enabled:videoEnabled,camera_preview_supported:true,camera_proxy_path:'/camera/stream',camera_url_masked:'Configured test camera',timelapse_state:timelapseState,app_version:'1.2.4',update_status:{checked:true,message:'No update'},system_check:{ray5_host_configured:true,ray5_http_reachable:online,ray5_websocket_reachable:online,page_id_captured:online,sd_card_list_working:online,camera_url_configured:cameraConfigured,camera_test_passed:true},comm_safety:{comm_lost_during_job:lockout,message:lockout?'Verify the Ray5 screen before continuing.':''}};}
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const json=(body,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  let body=null;
  if(req.method!=='GET'){
    assert.equal(req.headers['x-ray5-pilot-request'],'1');
    const chunks=[];for await(const chunk of req)chunks.push(chunk);const raw=Buffer.concat(chunks).toString();
    body=raw?(req.headers['content-type']?.includes('application/json')?JSON.parse(raw):{multipart:raw}):null;
    commands.push({url:url.pathname,method:req.method,body});
    if(holdRoute===url.pathname)await new Promise(resolve=>releaseHold=resolve);
    if(failRoute===url.pathname)return json({ok:false,error:'Fixture failure: '+url.pathname,message:'Fixture failure: '+url.pathname},503);
  }
  if(url.pathname==='/api/config')return json({ok:true,config});
  if(url.pathname==='/api/status')return json(status());
  if(url.pathname==='/api/jobs')return json({ok:true,jobs:emptyJobs?[]:jobs});
  if(url.pathname==='/api/files')return json({ok:true,path:'/',files:sdFiles,storage:{total:'8 GB',used:'1.2 GB',occupation:'15%',mode:'SD',status:'Ready'}});
  if(url.pathname==='/api/console')return json({ok:true,items:consoleItems});
  if(url.pathname==='/api/timelapse/state')return json({ok:true,state:timelapseState});
  if(url.pathname==='/api/timelapses'){
    const items=structuredClone(timelapses);
    if(holdTimelapseList){holdTimelapseList=false;await new Promise(resolve=>releaseTimelapseList=resolve);}
    return json({ok:true,items,sessions:[{session:'fixture_session',status:'recoverable',frame_count:126,last_modified:1794119300,message:'Preserved frames'}]});
  }
  if(url.pathname==='/api/snapshots')return json({ok:true,items:[{name:'latest.jpg',type:'processed',is_latest:true,size_bytes:12345,url:'/test/latest.jpg',download_url:'/test/latest.jpg?download=1'},{name:'latest_raw.jpg',type:'raw',is_latest:true,size_bytes:45678,url:'/test/latest_raw.jpg',download_url:'/test/latest_raw.jpg?download=1'}]});
  if(url.pathname==='/api/camera/video-enabled'){videoEnabled=!!body.enabled;return json({ok:true,enabled:videoEnabled});}
  if(url.pathname==='/api/timelapse/start'){timelapseState={enabled:true,active:true,armed:false};return json({ok:true,state:timelapseState,message:'Timelapse started.'});}
  if(url.pathname==='/api/timelapse/stop'){timelapseState={enabled:true,active:false,armed:false};return json({ok:true,state:timelapseState,message:'Timelapse saved.'});}
  if(url.pathname==='/api/safety/clear-comm-loss'){lockout=false;return json({ok:true});}
  if(url.pathname==='/api/unlock'){machineState='Idle';return json({ok:true,message:'Unlocked'});}
  if(url.pathname==='/api/laser/test-fire')return json({ok:true,s_value:50,duration_ms:1000,command:'M4'});
  if(url.pathname==='/api/console/clear'){consoleItems=[];return json({ok:true});}
  if(url.pathname==='/api/console/command'){consoleItems.push({ts:'10:42:02',level:'info',message:body.command+' -> ok'});return json({ok:true,command:body.command});}
  if(url.pathname==='/api/files/upload')return json({ok:true,filename:'upload_fixture.gc'});
  if(url.pathname==='/api/files/frame')return json(sdFrameUnavailable?{ok:false,download_unavailable:true,message:'Ray5 returned a web page instead of SD G-code. No motion sent.'}:{ok:true,message:'Frame sent for SD file. Laser remains off.'},sdFrameUnavailable?422:200);
  if(url.pathname==='/api/jobs/refresh-watched')return json({ok:true,imported:0,rejected:0});
  if(url.pathname==='/api/camera/capture')return json({ok:true,filename:'latest.jpg'});
  if(['/api/home','/api/preset-move','/api/manual/center','/api/move','/api/air/on','/api/air/off','/api/stop','/api/pause','/api/resume','/api/jobs/frame','/api/jobs/upload','/api/jobs/start','/api/jobs/import','/api/imported-files/delete','/api/files/start','/api/files/delete','/api/sd-files/delete','/api/timelapses/delete','/api/timelapses/recover','/api/timelapses/delete-session','/api/camera/test','/api/snapshots/open-folder'].includes(url.pathname)||(/^\/api\/jobs\/[^/]+$/.test(url.pathname)&&req.method==='DELETE'))return json({ok:true,message:'Fixture action accepted',deleted:[],failed:[]});
  if(url.pathname==='/camera/stream'||url.pathname.startsWith('/test/latest')){res.writeHead(200,{'Content-Type':'image/svg+xml'});res.end(image);return;}
  if(url.pathname==='/camera/calibration'){res.end('<h1>Calibration fixture</h1>');return;}
  if(url.pathname.startsWith('/api/')){unexpected.push(req.url);return json({ok:false,error:'Unexpected fixture API'},404);}
  const file=url.pathname==='/'?'web/templates/index.html':url.pathname.startsWith('/static/')?'web/'+url.pathname.slice(1):null;
  const target=file&&path.resolve(root,file);
  if(!target||!target.startsWith(root+path.sep)||!fs.existsSync(target)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.ico':'image/x-icon'})[path.extname(target)]||'application/octet-stream');res.end(fs.readFileSync(target));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM?{executablePath:process.env.PLAYWRIGHT_CHROMIUM}:{})});
 try{
 const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
   window.popupCalls=[];window.open=(...args)=>{window.popupCalls.push(args);return {closed:false,focus(){},close(){this.closed=true;}};};
   HTMLMediaElement.prototype.play=function(){this.dispatchEvent(new Event('play'));return Promise.resolve();};
   HTMLMediaElement.prototype.pause=function(){};HTMLMediaElement.prototype.load=function(){};
   Object.defineProperty(HTMLMediaElement.prototype,'src',{get(){return this.dataset.testSrc||'';},set(value){this.dataset.testSrc=value;}});
 });
 const nav=async name=>{await page.locator(`[data-dashboard-page="${name}"]`).click();};
 const fileTab=async name=>{await page.locator(`[data-file-tab="${name}"]`).click();};
 const manualReady=()=>page.waitForFunction(()=>!manualBusy);
 const call=async(selector,url,expectedBody,confirm=false)=>{
   const before=commands.filter(c=>c.url===url).length;
   if(confirm)page.once('dialog',d=>d.accept());
   await page.locator(selector).click();
   await page.waitForFunction(()=>!manualBusy);
   await page.waitForTimeout(30);
   const matches=commands.filter(c=>c.url===url);assert.equal(matches.length,before+1,`Expected one ${url}`);
   if(expectedBody!==undefined)assert.deepEqual(matches.at(-1).body,expectedBody,`Wrong payload ${url}`);
 };
 await page.goto(base+'/');await page.waitForFunction(()=>document.body.classList.contains('dashboard-ready')&&manualCfg.preset_enabled&&document.querySelectorAll('#jobsBody tr').length===2&&cameraConfigured);
 assert.equal(await page.locator('#dashboardNav button').count(),5);
 const original=execFileSync('git',['show','HEAD:web/templates/index.html'],{cwd:root,encoding:'utf8'});
 const ids=await page.locator('[id]').evaluateAll(els=>els.map(el=>el.id));assert.equal(ids.length,new Set(ids).size);
 for(const [,id] of original.matchAll(/\bid="([^"]+)"/g))assert(ids.includes(id),'Missing original control '+id);
 const originalCount=[...original.matchAll(/\bid="([^"]+)"/g)].length;
 assert.equal(await page.locator('#stop').count(),1);assert.equal(await page.locator('#stop').evaluate(el=>el.parentElement.id),'dashboardTopActions');
 const positions=await page.locator('#dashboardWorkspaceView').evaluate(el=>Object.fromEntries(['cameraCard','manualControlsCard','statusCard'].map(id=>{const r=el.querySelector('#'+id).getBoundingClientRect();return [id,{y:r.y,bottom:r.bottom}];})));
 assert(Math.abs(positions.cameraCard.y-positions.manualControlsCard.y)<1);assert(positions.statusCard.y>positions.manualControlsCard.bottom);
 // The diagonal arrows still use the original IDs and exact motion payloads.
 assert.deepEqual(await page.locator('#xyMinusPlus,#xyPlusPlus,#xyMinusMinus,#xyPlusMinus').allTextContents(),['\u2196','\u2197','\u2199','\u2198']);
 await page.locator('#jogStep').selectOption('10');await page.locator('#jogFeed').selectOption('1000');
 await call('#homeAll','/api/home',{axis:'all'});
 await call('#presetMoveBtn','/api/preset-move',{});
 for(const [id,body] of [['xMinus',{axis:'x',distance:-10,feedrate:1000}],['xPlus',{axis:'x',distance:10,feedrate:1000}],['yMinus',{axis:'y',distance:-10,feedrate:1000}],['yPlus',{axis:'y',distance:10,feedrate:1000}],['xyMinusPlus',{dx:-10,dy:10,feedrate:1000}],['xyPlusPlus',{dx:10,dy:10,feedrate:1000}],['xyMinusMinus',{dx:-10,dy:-10,feedrate:1000}],['xyPlusMinus',{dx:10,dy:-10,feedrate:1000}]])await call('#'+id,'/api/move',body);
 await call('#centerBed','/api/manual/center',{});await call('#unlock','/api/unlock',{});
 await call('#airOn','/api/air/on',{});await call('#airOff','/api/air/off',{});
 await call('#pauseBtn','/api/pause',{},true);await call('#resumeBtn','/api/resume',{});
 await page.locator('.dashboard-laser-tools summary').click();
 const beforeCancel=commands.length;page.once('dialog',d=>d.dismiss());await page.locator('#testFire').click();assert.equal(commands.length,beforeCancel,'Cancelled laser test must not send');
 await call('#testFire','/api/laser/test-fire',{s_value:50,duration_ms:1000},true);
 await page.locator('.dashboard-laser-tools summary').click();
 // Stop must remain usable while a manual request is still in flight.
 holdRoute='/api/home';releaseHold=null;
 await page.locator('#homeAll').click();
 await page.waitForFunction(()=>manualBusy);
 for(let n=0;!releaseHold&&n<100;n++)await new Promise(resolve=>setTimeout(resolve,10));
 assert(releaseHold,'Home request should be held');
 assert(await page.locator('#stop').isEnabled());
 const stopsBefore=commands.filter(c=>c.url==='/api/stop').length;
 page.once('dialog',d=>d.accept());await page.locator('#stop').click();
 await page.waitForFunction(()=>!stopRequestPending);
 assert.equal(commands.filter(c=>c.url==='/api/stop').length,stopsBefore+1);
 assert(await page.locator('#xPlus').isDisabled(),'Pending Home must still keep jog locked');
 holdRoute='';releaseHold();await manualReady();
 await page.evaluate(()=>{manualCfg.test_fire_enabled=false;setManualBusy(true);setManualBusy(false);});
 assert(await page.locator('#testFire').isDisabled(),'Other actions must not re-enable a disabled laser test');
 await page.evaluate(()=>{manualCfg.test_fire_enabled=true;setManualBusy(false);});
 // Original DOM nodes, handlers, inputs and selections survive switching sections.
 await page.evaluate(()=>{window.originalJobsCard=document.getElementById('importedJobsCard');window.originalJogButton=document.getElementById('xPlus');window.originalJogHandler=originalJogButton.onclick;window.originalCameraParent=document.getElementById('cameraCard').parentElement;});
 await page.locator('#jobsBody input[type="checkbox"]').first().check();
 await nav('files');await nav('camera');await nav('console');await nav('workspace');
 assert(await page.evaluate(()=>originalJobsCard===document.getElementById('importedJobsCard')&&originalJogButton===document.getElementById('xPlus')));
 assert.equal(await page.locator('#jogFeed').inputValue(),'1000');assert(await page.locator('#jobsBody input[type="checkbox"]').first().isChecked());
 assert(await page.evaluate(()=>originalJogHandler===document.getElementById('xPlus').onclick&&originalCameraParent===document.getElementById('cameraCard').parentElement));
 // Imported job actions retain the local filename and distinct upload/start routes.
 await call('#jobsBody tr:first-child button:nth-child(1)','/api/jobs/frame',{filename:'fixture_grid.gc'});
 await call('#jobsBody tr:first-child button:nth-child(2)','/api/jobs/upload',{filename:'fixture_grid.gc'});
 await call('#jobsBody tr:first-child button:nth-child(3)','/api/jobs/start',{filename:'fixture_grid.gc'},true);
 failRoute='/api/jobs/start';await call('#jobsBody tr:first-child button:nth-child(3)','/api/jobs/start',{filename:'fixture_grid.gc'},true);assert((await page.locator('#jobsMsg').textContent()).includes('Fixture failure'));failRoute='';
 await call('#jobsBody tr:first-child button:nth-child(4)','/api/jobs/fixture_grid.gc',null,true);
 await nav('files');await call('#jobsRefresh','/api/jobs/refresh-watched',null);
 await page.locator('#jobFile').setInputFiles({name:'import_fixture.gc',mimeType:'text/plain',buffer:Buffer.from('G0 X0 Y0\nM5\n')});
 await call('#importBtn','/api/jobs/import');assert(commands.at(-1).body.multipart.includes('import_fixture.gc'));
 await page.locator('#jobsSelectAll').check();await page.waitForFunction(()=>document.getElementById('jobsSelectedCount').textContent==='2 selected');
 await call('#jobsDeleteSelected','/api/imported-files/delete',{filenames:jobs.map(j=>j.name)},true);
 assert(await page.locator('#jobsClearSelection').isDisabled());await page.locator('#jobsSelectAll').check();await page.waitForFunction(()=>!document.getElementById('jobsClearSelection').disabled);await page.locator('#jobsClearSelection').click();
 // SD actions use the machine filename/path, never an imported-job name.
 await fileTab('sd');await call('#sdFilesBody tr:first-child button:first-child','/api/files/start',{filename:'LightBurn_001.gc',path:'/'},true);
 const sdFrame=page.locator('#sdFilesBody tr:first-child .sd-frame-btn');
 assert(await sdFrame.isEnabled());
 const beforeFrameCancel=commands.length;page.once('dialog',d=>d.dismiss());await sdFrame.click();await page.waitForFunction(()=>!sdFrameBusy);assert.equal(commands.length,beforeFrameCancel);
 const runSdFrame=async()=>{
   const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/files/frame');
   page.once('dialog',d=>d.accept());await sdFrame.click();await response;await page.waitForFunction(()=>!sdFrameBusy);
 };
 await runSdFrame();assert.deepEqual(commands.findLast(c=>c.url==='/api/files/frame').body,{filename:'LightBurn_001.gc',path:'/',confirmed:true});
 assert((await page.locator('#sdMsg').textContent()).includes('Laser remains off'));
 sdFrameUnavailable=true;await runSdFrame();assert(await sdFrame.isDisabled());assert((await page.locator('#sdMsg').textContent()).includes('No motion sent'));
 sdFrameUnavailable=false;await page.evaluate(()=>loadSdFiles({preserveMessage:true}));assert(await sdFrame.isEnabled());
 machineState='Alarm';await page.evaluate(()=>refreshStatus());assert(await sdFrame.isDisabled());
 machineState='Run';await page.evaluate(()=>refreshStatus());assert(await sdFrame.isDisabled());
 machineState='Idle';online=false;await page.evaluate(()=>refreshStatus());assert(await sdFrame.isDisabled());
 online=true;await page.evaluate(()=>refreshStatus());assert(await sdFrame.isEnabled());
 // Stop stays usable during an SD read/frame and does not release the motion lock early.
 holdRoute='/api/files/frame';releaseHold=null;
 page.once('dialog',d=>d.accept());await sdFrame.click();
 await page.waitForFunction(()=>sdFrameBusy&&manualBusy);
 for(let n=0;!releaseHold&&n<100;n++)await new Promise(resolve=>setTimeout(resolve,10));
 assert(releaseHold,'SD frame request should be held');
 assert(await page.locator('#stop').isEnabled());
 const sdStopsBefore=commands.filter(c=>c.url==='/api/stop').length;
 page.once('dialog',d=>d.accept());await page.locator('#stop').click();
 await page.waitForFunction(()=>!stopRequestPending);
 assert.equal(commands.filter(c=>c.url==='/api/stop').length,sdStopsBefore+1);
 assert(await page.evaluate(()=>manualBusy),'Pending SD frame must keep jog locked after Stop');
 holdRoute='';releaseHold();await page.waitForFunction(()=>!sdFrameBusy&&!manualBusy);
 await call('#sdFilesBody tr:first-child button:last-child','/api/files/delete',{filename:'LightBurn_001.gc',path:'/'},true);
 await page.locator('#sdUploadFile').setInputFiles({name:'upload_fixture.gc',mimeType:'text/plain',buffer:Buffer.from('M5\nG0 X0 Y0\n')});await call('#sdUploadBtn','/api/files/upload');
 assert(commands.findLast(c=>c.url==='/api/files/upload').body.multipart.includes('upload_fixture.gc'));
 await page.locator('#sdSelectAll').check();await page.waitForFunction(()=>document.getElementById('sdSelectedCount').textContent==='2 selected');
 await call('#sdDeleteSelected','/api/sd-files/delete',{files:sdFiles.map(f=>({name:f.name,path:f.path})),path:'/'},true);
 await page.locator('#sdSelectAll').check();await page.waitForFunction(()=>!document.getElementById('sdClearSelection').disabled);await page.locator('#sdClearSelection').click();await call('#sdStop','/api/stop',{},true);
 // Global Stop is visible and uses the same existing handler on every section.
 for(const section of ['workspace','files','camera','timelapse','console']){await nav(section);await call('#stop','/api/stop',{},true);assert((await page.locator('#dashboardMessage').textContent()).includes('OK:'));}
 // Snapshot, calibration and video buttons retain their original behavior.
 await nav('camera');await call('#camCapture','/api/camera/capture',null);await call('#snapOpenFolder','/api/snapshots/open-folder',null);
 assert.equal(await page.locator('#openLatestSnapshot').getAttribute('href'),'/test/latest.jpg');assert.equal(await page.locator('#openLatestRaw').getAttribute('href'),'/test/latest_raw.jpg');
 await page.locator('.dashboard-camera-tools summary').click();await call('#camTest','/api/camera/test',null);
 await page.locator('#camCalibrate').click();assert(await page.locator('#camera-calibration-modal').isVisible());assert.equal(await page.locator('#camera-calibration-frame').getAttribute('src'),'/camera/calibration');
 await page.locator('#open-calibration-window').click();await page.locator('#close-calibration-modal').click();assert(!(await page.locator('#camera-calibration-modal').isVisible()));
 await call('#camVideoToggle','/api/camera/video-enabled',{enabled:false});await call('#camVideoToggle','/api/camera/video-enabled',{enabled:true});
 await page.locator('#camRefresh').click();await page.locator('#camPopout').click();assert((await page.evaluate(()=>popupCalls)).some(args=>args[0]==='/camera/popout'));
 await page.locator('#camVideoToggle').click();await page.waitForFunction(()=>!cameraVideoEnabled);await page.locator('#camVideoToggle').click();await page.waitForFunction(()=>cameraVideoEnabled);
 // Timelapse library and recovery remain available; Play brings the existing player into view.
 await nav('timelapse');await call('#timelapseStart','/api/timelapse/start',{job_source:'manual'});await call('#timelapseStop','/api/timelapse/stop',{},true);
 await call('#timelapseSessionsBody button:first-child','/api/timelapses/recover',{session:'fixture_session'},true);
 await call('#timelapseSessionsBody button:last-child','/api/timelapses/delete-session',{session:'fixture_session'},true);
 await page.locator('#timelapseBody tr:first-child button').click();await page.waitForFunction(()=>document.getElementById('dashboardWorkspaceView').hidden===false&&currentTimelapsePlaybackFile==='fixture_run.mp4');assert(await page.locator('#timelapsePlayer').isVisible());
 await nav('timelapse');await page.locator('#timelapseSelectAll').check();await page.waitForFunction(()=>document.getElementById('timelapseSelectedCount').textContent==='2 selected');await call('#timelapseDeleteSelected','/api/timelapses/delete',{filenames:timelapses.map(t=>t.name)},true);
 await page.locator('#timelapseSelectAll').check();await page.waitForFunction(()=>!document.getElementById('timelapseClearSelection').disabled);await page.locator('#timelapseClearSelection').click();
 // An older overlapping refresh must neither duplicate nor replace the newest timelapse list.
 holdTimelapseList=true;await page.evaluate(()=>{window.pendingTimelapseRead=loadTimelapses();});
 for(let n=0;!releaseTimelapseList&&n<100;n++)await new Promise(resolve=>setTimeout(resolve,10));
 assert(releaseTimelapseList,'First timelapse request should be held');
 timelapses.push({name:'newly_finished.mp4',url:'/test/new.mp4',size_bytes:1000,modified:1794121000});
 await page.evaluate(()=>loadTimelapses());releaseTimelapseList();await page.evaluate(()=>pendingTimelapseRead);
 assert.equal(await page.locator('#timelapseBody tr').count(),3);
 assert((await page.locator('#timelapseBody').textContent()).includes('newly_finished.mp4'));
 timelapses.pop();await page.evaluate(()=>loadTimelapses());
 // Console input, history, clear, status details, Alarm and safety recovery.
 await nav('console');await page.locator('#consoleCommandInput').fill('?');await call('#consoleCommandSend','/api/console/command',{command:'?'});
 await page.locator('#consoleCommandInput').press('ArrowUp');assert.equal(await page.locator('#consoleCommandInput').inputValue(),'?');await call('#consoleClear','/api/console/clear',null);
 await page.locator('#dashboardStatusDetails summary').click();await page.evaluate(()=>refreshStatus());assert(await page.locator('#dashboardStatusDetails').getAttribute('open')!==null);
 machineState='Alarm';await page.evaluate(()=>refreshStatus());assert.equal(await page.locator('#machineStateBadge').textContent(),'Alarm');assert(await page.locator('#dashboardMachineAlert').isVisible());await call('#dashboardUnlock','/api/unlock',{});assert(!(await page.locator('#dashboardUnlock').isVisible()));
 online=false;lockout=true;await page.evaluate(()=>refreshStatus());assert.equal(await page.locator('#machineStateBadge').textContent(),'Disconnected');assert(await page.locator('#dashboardClearLockout').isVisible());await call('#dashboardClearLockout','/api/safety/clear-comm-loss',{},true);assert(!(await page.locator('#dashboardClearLockout').isVisible()));
 online=true;await page.evaluate(()=>refreshStatus());
 // An empty colspan row must span the grid, not stack words in its selection column.
 emptyJobs=true;await page.evaluate(()=>refreshJobs());
 for(const width of [1280,1024,768,375,320]){
   await page.setViewportSize({width,height:1000});await nav('workspace');await fileTab('imported');
   const jogAlignment=await page.locator('.jog-btn').evaluateAll(buttons=>buttons.map(button=>{
     const style=getComputedStyle(button),box=button.getBoundingClientRect();
     const range=document.createRange();range.selectNodeContents(button);const text=range.getBoundingClientRect();
     return {id:button.id,align:style.alignItems,justify:style.justifyContent,textAlign:style.textAlign,
       offsetX:Math.abs((text.left+text.right-box.left-box.right)/2),offsetY:Math.abs((text.top+text.bottom-box.top-box.bottom)/2)};
   }));
   assert.equal(jogAlignment.length,9);
   for(const button of jogAlignment){
     assert.equal(button.align,'center',`${button.id} vertical alignment at ${width}`);
     assert.equal(button.justify,'center',`${button.id} horizontal alignment at ${width}`);
     assert.equal(button.textAlign,'center');
     assert(button.offsetX<=1&&button.offsetY<=3,`Off-center jog content at ${width}: ${JSON.stringify(button)}`);
   }
   if(width===1280||width===375)await page.locator('.jog-pad').screenshot({path:path.join(output,`centered-jog-${width}.png`)});
   const empty=page.locator('#jobsBody td[colspan]');
   assert((await empty.textContent()).startsWith('No imported jobs yet.'));
   const sizes=await empty.evaluate(td=>({width:td.getBoundingClientRect().width,height:td.getBoundingClientRect().height,bodyWidth:td.closest('tbody').getBoundingClientRect().width}));
   assert(sizes.width>sizes.bodyWidth*.95,`Empty message must span full width at ${width}: ${JSON.stringify(sizes)}`);
   assert(sizes.height<160,`Empty message stacked vertically at ${width}`);
   if(width===1280||width===375)await page.locator('#importedJobsCard').screenshot({path:path.join(output,`empty-jobs-${width}.png`)});
   await nav('files');assert(await empty.isVisible());
 }
 emptyJobs=false;await page.evaluate(()=>refreshJobs());
 // Responsive layouts: no duplicate IDs or controls clipped outside their tables.
 for(const width of [1280,1024,768,375,320]){
   await page.setViewportSize({width,height:1000});
   for(const section of ['workspace','files','camera','timelapse','console']){
     await nav(section);
     assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Page overflow ${width} ${section}`);
     const clipped=await page.locator('button:visible,input:visible,select:visible').evaluateAll(els=>els.filter(el=>{if(el.closest('.table-wrap'))return false;const r=el.getBoundingClientRect();return r.left<0||r.right>innerWidth+1;}).map(el=>el.id));
     assert.deepEqual(clipped,[],`Clipped controls ${width} ${section}`);
     if(section==='workspace'&&width<580){const ys=await page.evaluate(()=>['cameraCard','manualControlsCard','statusCard','dashboardFileGroup'].map(id=>document.getElementById(id).getBoundingClientRect().y));assert(ys.every((y,i)=>!i||y>ys[i-1]),'Mobile order camera/controls/status/jobs');}
   }
 }
 await nav('camera');await page.evaluate(async()=>{await setCameraVideoEnabled(true);stopTimelapsePlayback(false);await refreshStatus();document.getElementById('dashboardStatusDetails').open=false;document.querySelector('.dashboard-camera-tools').open=false;});
 await page.setViewportSize({width:1280,height:1000});await nav('workspace');await fileTab('imported');await page.screenshot({path:path.join(output,'workspace-desktop.png'),fullPage:true});
 await nav('files');await fileTab('sd');await page.screenshot({path:path.join(output,'sd-files-desktop.png'),fullPage:true});
 await page.setViewportSize({width:375,height:1000});await nav('workspace');await fileTab('imported');await page.screenshot({path:path.join(output,'workspace-mobile.png'),fullPage:true});
 assert.deepEqual(errors,[],'Browser runtime errors');assert.deepEqual(unexpected,[],'Unmatched routes');await page.close();
 // If the presentation module is unavailable, the original core controls still bind.
 const fallback=await browser.newPage();await fallback.route('**/static/dashboard-layout.js*',route=>route.abort());await fallback.goto(base+'/');await fallback.waitForFunction(()=>typeof document.getElementById('homeAll').onclick==='function');assert(await fallback.locator('#homeAll').isVisible());assert(await fallback.locator('#stop').isVisible());await fallback.close();
 config.safety.test_fire_enabled=false;config.console.raw_command_enabled=false;
 const locked=await browser.newPage();await locked.goto(base+'/');await locked.waitForFunction(()=>!manualCfg.test_fire_enabled&&!manualCfg.raw_command_enabled);assert(await locked.locator('#testFire').isDisabled());assert(!(await locked.locator('#consoleCommandWrap').isVisible()));await locked.locator('[data-dashboard-page="files"]').click();await locked.locator('[data-dashboard-page="workspace"]').click();assert(await locked.locator('#testFire').isDisabled());await locked.close();
 console.log(JSON.stringify({passed:true,originalIdsPreserved:originalCount,categories:5,actionRequests:commands.length,widths:[1280,1024,768,375,320],runtimeErrors:errors,screenshots:output},null,2));
 }finally{if(releaseHold)releaseHold();await browser.close();server.closeAllConnections();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;server.closeAllConnections();server.close();});

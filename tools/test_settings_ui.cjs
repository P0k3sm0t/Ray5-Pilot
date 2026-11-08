/* Run with node; PLAYWRIGHT_MODULE and PLAYWRIGHT_CHROMIUM may point at local test tools. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'build', 'settings-ui-test');
fs.mkdirSync(output, {recursive:true});
const initial = JSON.parse(fs.readFileSync(path.join(root, 'config.example.json'), 'utf8').replace(/^\uFEFF/, ''));
initial.ray5.host = '192.0.2.10';
initial.camera.enabled = false;
initial.camera.url = '';
let config = structuredClone(initial);
let failSave = false;
let failLoad = false;
let delaySave = 0;
let posted = null;
let saveCount = 0;
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const json = (body, status=200) => {res.writeHead(status, {'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  if (url.pathname === '/api/config' && req.method === 'GET') {
    return failLoad ? json({ok:false, error:'Test config load failed'}, 500) : json({ok:true, config});
  }
  if (url.pathname === '/api/config' && req.method === 'POST') {
    assert.equal(req.headers['x-ray5-pilot-request'], '1');
    const chunks=[];for await (const chunk of req) chunks.push(chunk);
    posted=JSON.parse(Buffer.concat(chunks));saveCount++;
    if (delaySave) await new Promise(resolve=>setTimeout(resolve,delaySave));
    if (failSave) return json({ok:false,error:'Test save rejected'},400);
    const merge=(a,b)=>{for(const [key,value] of Object.entries(b)) {if(value && typeof value==='object' && !Array.isArray(value)) a[key]=merge(a[key]||{},value); else a[key]=value;}return a;};
    config=merge(config,posted);
    return json({ok:true});
  }
  // An unavailable update service must never block configuration or Save.
  if(url.pathname.startsWith('/api/github/')) return json({ok:false,checked:true,checking:false,message:'Offline test'});
  if(url.pathname.startsWith('/api/')) return json({ok:false,error:'Unexpected API request'},404);
  const file = url.pathname === '/setup' ? 'web/templates/setup.html' : url.pathname.startsWith('/static/') ? 'web/'+url.pathname.slice(1) : null;
  if(!file) {res.writeHead(404);res.end();return;}
  const target=path.resolve(root,file);
  if(!target.startsWith(root+path.sep) || !fs.existsSync(target)) {res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type', ({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.ico':'image/x-icon'})[path.extname(target)]||'application/octet-stream');
  res.end(fs.readFileSync(target));
});

(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM?{executablePath:process.env.PLAYWRIGHT_CHROMIUM}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:950}});
    const errors=[];
    page.on('pageerror',err=>errors.push(err.message));
    const original=execFileSync('git',['show','HEAD:web/templates/setup.html'],{cwd:root,encoding:'utf8'});
    const originalIds=[...original.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
    await page.goto(base+'/setup');
    await page.waitForFunction(()=>document.getElementById('saveCfg').disabled===false);
    assert.equal(await page.locator('#settingsNav button').count(),7);
    const ids=await page.locator('[id]').evaluateAll(els=>els.map(el=>el.id));
    assert.equal(new Set(ids).size,ids.length,'Duplicate HTML IDs');
    for(const id of originalIds) assert(ids.includes(id),`Lost original ID ${id}`);
    assert.equal(await page.locator('#ray_host').inputValue(),'192.0.2.10');
    const cleanPayload=await page.evaluate(()=>collect());
    assert.equal(await page.locator('.settings-category:visible').count(),1);
    await page.screenshot({path:path.join(output,'connection-desktop.png'),fullPage:true});
    await page.locator('#ray_host').fill('192.0.2.20');
    await page.locator('#settings-nav-camera').click();
    await page.locator('#cam_align_width_mm').fill('310');
    assert.equal(await page.locator('#settingsDirtyState').textContent(),'Unsaved changes');
    await page.locator('#settings-nav-connection').click();
    assert.equal(await page.locator('#ray_host').inputValue(),'192.0.2.20');
    await page.locator('#discardCfg').click();
    assert.equal(await page.locator('#ray_host').inputValue(),'192.0.2.10');
    assert.deepEqual(await page.evaluate(()=>collect()),cleanPayload,'Discard must restore every field');
    await page.locator('#settings-nav-motion').click();
    await page.locator('#frame_feed').fill('700');
    await page.locator('#settings-nav-camera').click();
    await page.locator('#cam_align_width_mm').fill('310');
    const expected=await page.evaluate(()=>collect());
    await page.locator('#saveCfg').click();
    await page.waitForFunction(()=>document.getElementById('saveOut').textContent.startsWith('Config saved successfully'));
    assert.deepEqual(posted,expected,'Existing collect mapping must send all category fields');
    assert.equal(posted.framing.feedrate,700);
    assert.equal(posted.camera.overlay_alignment.physical_width_mm,310);
    assert.equal(await page.locator('#settingsDirtyState').textContent(),'All changes saved');
    // Persisted values must load again after reload, including fields in closed details.
    await page.reload();
    await page.waitForFunction(()=>document.getElementById('saveCfg').disabled===false);
    assert.equal(await page.locator('#frame_feed').inputValue(),'700');
    assert.equal(await page.locator('#cam_align_width_mm').inputValue(),'310');
    await page.locator('#ray_host').fill('192.0.2.30');
    failSave=true;
    await page.locator('#saveCfg').click();
    await page.waitForFunction(()=>document.getElementById('saveOut').textContent.includes('Test save rejected'));
    assert.equal(await page.locator('#settingsDirtyState').textContent(),'Unsaved changes');
    assert.equal(await page.locator('#saveCfg').isDisabled(),false);
    failSave=false;
    await page.locator('#saveCfg').click();
    await page.waitForFunction(()=>document.getElementById('settingsDirtyState').textContent==='All changes saved');
    delaySave=300;
    await page.locator('#ray_host').fill('192.0.2.40');
    await page.locator('#saveCfg').click();
    await page.locator('#ray_host').fill('192.0.2.50');
    await page.waitForFunction(()=>document.getElementById('saveCfg').disabled===false);
    assert.equal(await page.locator('#settingsDirtyState').textContent(),'Unsaved changes','Changes made during save stay pending');
    await page.locator('#discardCfg').click();
    assert.equal(await page.locator('#ray_host').inputValue(),'192.0.2.40');
    delaySave=0;
    // Check all categories and expanded advanced sections at several screen widths.
    for(const width of [1280,768,375,320]){
      await page.setViewportSize({width,height:950});
      for(const name of ['connection','camera','jobs','motion','safety','app','advanced']){
        await page.locator('#settings-nav-'+name).click();
        await page.locator('.settings-category:visible details').evaluateAll(els=>els.forEach(el=>el.open=true));
        assert.equal(await page.locator('.settings-category:visible').count(),1);
        const overflowing=await page.evaluate(()=>Array.from(document.querySelectorAll('.settings-category:not([hidden]) input,.settings-category:not([hidden]) select,.settings-savebar')).filter(el=>{const r=el.getBoundingClientRect();return r.right>innerWidth+1||r.left<0;}).map(el=>el.id||el.className));
        assert.deepEqual(overflowing,[],`${width}px ${name} clipped controls`);
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width}px ${name} page overflow`);
      }
    }
    await page.locator('#settings-nav-camera').click();
    await page.locator('.settings-category:visible details').evaluateAll(els=>els.forEach(el=>el.open=false));
    await page.screenshot({path:path.join(output,'camera-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1280,height:950});
    await page.screenshot({path:path.join(output,'camera-desktop.png'),fullPage:true});
    // Model an offline update check that never returns at all.
    await page.route('**/api/github/**',route=>new Promise(()=>{}));
    await page.reload();
    await page.waitForFunction(()=>document.getElementById('saveCfg').disabled===false,{timeout:3000});
    assert.equal(await page.locator('#ray_host').inputValue(),'192.0.2.40');
    await page.unrouteAll({behavior:'ignoreErrors'});
    await page.close();
    const broken=await browser.newPage();
    failLoad=true;
    await broken.goto(base+'/setup');
    await broken.waitForFunction(()=>document.getElementById('settingsDirtyState').textContent==='Settings unavailable');
    assert(await broken.locator('#saveCfg').isDisabled());
    assert(await broken.locator('#discardCfg').isDisabled());
    await broken.close();
    assert.deepEqual(errors,[],'Browser runtime errors');
    fs.writeFileSync(path.join(output,'saved-payload.json'),JSON.stringify(posted,null,2));
    console.log(JSON.stringify({passed:true,categories:7,originalIdsPreserved:originalIds.length,saveRequests:saveCount,widths:[1280,768,375,320],runtimeErrors:errors,screenshots:output},null,2));
  }finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(err=>{console.error(err);process.exitCode=1;server.closeAllConnections();server.close();});

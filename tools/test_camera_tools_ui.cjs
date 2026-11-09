/* Isolated camera-tool fixtures. No camera, Ray5, or personal config is accessed. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),output=path.join(root,'build/camera-tools-ui-test');
fs.mkdirSync(output,{recursive:true});
const originalConfig={ray5:{host:'YOUR_RAY5_IP'},camera:{deskew:{enabled:true,source_points:[],output_size:[1200,1200]},postprocess:{rotate_degrees:90},overlay_alignment:{source_offset_x_px:12,source_offset_y_px:-4,fine_rotation_degrees:0.5}}};
let config=structuredClone(originalConfig),writes=[],captures=0,streams=0,rawReads=0;
let failConfig=false,failSave=false,failCapture=false,failImage=false,failStream=false;
const unexpected=[],errors=[];
const raw='<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#101b26"/><path d="M100 60H900V540H100Z" fill="#263e51" stroke="#9cbfff" stroke-width="4"/><path d="M100 300H900M500 60V540" stroke="#4a6579" stroke-width="2"/><text x="500" y="320" text-anchor="middle" font-family="sans-serif" font-size="30" fill="#c6d7e7">Calibration reference fixture</text></svg>';
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const json=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  const image=()=>{res.writeHead(200,{'Content-Type':'image/svg+xml'});res.end(raw);};
  if(url.pathname==='/api/config') {
    if(req.method==='GET')return json(failConfig?{ok:false,error:'Fixture config unavailable'}:{ok:true,config},failConfig?503:200);
    assert.equal(req.method,'POST');assert.equal(req.headers['x-ray5-pilot-request'],'1','Calibration must pass request guard');
    const chunks=[];for await(const chunk of req)chunks.push(chunk);const data=JSON.parse(Buffer.concat(chunks).toString());
    writes.push(data);if(failSave)return json({ok:false,error:'Fixture save failed'},500);
    config=structuredClone(data);return json({ok:true});
  }
  if(url.pathname==='/api/camera/capture'){
    assert.equal(req.method,'POST');assert.equal(req.headers['x-ray5-pilot-request'],'1');captures++;
    return json(failCapture?{ok:false,error:'Fixture camera offline'}:{ok:true},failCapture?503:200);
  }
  if(url.pathname==='/api/snapshots/open/latest_raw.jpg'){
    rawReads++;if(failImage){res.writeHead(404);res.end();return;}return image();
  }
  if(url.pathname==='/camera/stream'){
    streams++;if(failStream){res.writeHead(503);res.end();return;}return image();
  }
  if(url.pathname==='/embed'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><body style="margin:0"><iframe title="Calibration test" src="/camera/calibration" style="display:block;width:100%;height:1000px;border:0"></iframe></body>');return;}
  const template={'/camera/popout':'camera_popout.html','/camera/calibration':'camera_calibration.html','/camera-calibration':'camera_calibration.html'}[url.pathname];
  const target=template?path.join(root,'web/templates',template):url.pathname.startsWith('/static/')?path.resolve(root,'web',url.pathname.slice(1)):null;
  if(target&&target.startsWith(root+path.sep)&&fs.existsSync(target)){
    res.setHeader('Content-Type',({'.html':'text/html','.css':'text/css','.svg':'image/svg+xml','.js':'text/javascript','.ico':'image/x-icon'})[path.extname(target)]||'application/octet-stream');res.end(fs.readFileSync(target));return;
  }
  unexpected.push({method:req.method,path:url.pathname});res.writeHead(404);res.end();
});

(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM?{executablePath:process.env.PLAYWRIGHT_CHROMIUM}:{})});
  const context=await browser.newContext({viewport:{width:1280,height:1000}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{window.closeCalls=0;window.close=()=>window.closeCalls++;});
  const readyImage=()=>page.waitForFunction(()=>document.getElementById('calImg').naturalWidth===1000&&!document.getElementById('stage').hidden);
  const assertNoOverflow=async(width)=>{
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Page overflow at ${width}`);
    const clipped=await page.locator('button:visible,a:visible').evaluateAll(nodes=>nodes.filter(el=>{const r=el.getBoundingClientRect();return r.left<0||r.right>innerWidth+1;}).map(el=>el.id||el.textContent));
    assert.deepEqual(clipped,[],`Clipped controls at ${width}`);
    const ids=await page.locator('[id]').evaluateAll(nodes=>nodes.map(el=>el.id));assert.equal(ids.length,new Set(ids).size);
  };
  const assertOriginalIds=async(template)=>{
    const before=execFileSync('git',['show','HEAD:web/templates/'+template],{cwd:root,encoding:'utf8'});
    for(const [,id] of before.matchAll(/\bid="([^"]+)"/g))assert.equal(await page.locator('#'+id).count(),1,`Preserve ${template} control ${id}`);
  };
  try{
    await page.goto(base+'/camera/popout');await page.waitForFunction(()=>document.getElementById('popoutStatus').dataset.state==='live');
    await assertOriginalIds('camera_popout.html');
    for(const width of [1280,768,375,320]){
      await page.setViewportSize({width,height:1000});await assertNoOverflow(width);
      const fits=await page.locator('#popoutFeed').evaluate(el=>{const a=el.getBoundingClientRect(),b=el.parentElement.getBoundingClientRect();return a.width<=b.width&&a.height<=b.height;});assert(fits);
      if(width===1280||width===375)await page.screenshot({path:path.join(output,`popout-${width}.png`),fullPage:true});
    }
    failStream=true;await page.locator('#popoutRefresh').click();await page.waitForFunction(()=>document.getElementById('popoutStatus').dataset.state==='offline');
    assert(await page.locator('#popoutPlaceholder').isVisible());assert.equal(await page.locator('#popoutFeed').getAttribute('src'),null);
    failStream=false;await page.locator('#popoutRefresh').click();await page.waitForFunction(()=>document.getElementById('popoutStatus').dataset.state==='live');
    await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>closeCalls),1);
    await page.locator('#popoutClose').click();assert.equal(await page.evaluate(()=>closeCalls),2);
    await page.evaluate(()=>dispatchEvent(new Event('pagehide')));assert.equal(await page.locator('#popoutFeed').getAttribute('src'),null);
    await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
    await page.waitForFunction(()=>document.getElementById('popoutStatus').dataset.state==='live'&&document.getElementById('popoutFeed').hasAttribute('src'));

    await page.setViewportSize({width:1280,height:1000});await page.goto(base+'/camera/calibration');await readyImage();
    await assertOriginalIds('camera_calibration.html');
    assert.equal(writes.length,0);assert.equal(captures,0);
    assert.equal(await page.locator('#metaRot').textContent(),'90 deg');assert.equal(await page.locator('#metaOff').textContent(),'12, -4 px');
    await page.locator('#savePts').click();assert((await page.locator('#msg').textContent()).includes('Set all 4'));assert.equal(writes.length,0);
    for(const width of [1280,768,375,320]){
      await page.setViewportSize({width,height:1000});await assertNoOverflow(width);
      await page.locator('#resetPts').click();
      for(const [x,y] of [[.1,.1],[.9,.1],[.9,.9],[.1,.9]]){
        const box=await page.locator('#calImg').boundingBox();await page.mouse.click(box.x+box.width*x,box.y+box.height*y);
      }
      assert.equal(await page.locator('#ov circle').count(),4);assert.equal(writes.length,0,'Point selection must not save');
      const coords=await page.evaluate(()=>points.map(p=>[p.x,p.y]));
      const imageBox=await page.locator('#calImg').boundingBox();
      for(const [i,expected] of [[100,60],[900,60],[900,540],[100,540]].entries()){
        // Mouse events quantize to CSS pixels; a small preview can map one click pixel to several source pixels.
        assert(Math.abs(coords[i][0]-expected[0])<=1000/imageBox.width+0.1&&Math.abs(coords[i][1]-expected[1])<=600/imageBox.height+0.1,`Natural-pixel mapping at ${width}: ${JSON.stringify(coords)}`);
      }
      const aligned=await page.locator('#ov circle').evaluateAll(nodes=>nodes.every(c=>{const a=c.getBoundingClientRect(),b=c.ownerSVGElement.getBoundingClientRect();return a.left>=b.left&&a.right<=b.right&&a.top>=b.top&&a.bottom<=b.bottom;}));assert(aligned);
      if(width===1280||width===375)await page.screenshot({path:path.join(output,`calibration-${width}.png`),fullPage:true});
    }
    await page.locator('#savePts').click();await page.waitForFunction(()=>document.getElementById('msg').textContent==='Calibration points saved.');
    assert.equal(writes.length,1);assert.equal(writes[0].camera.deskew.enabled,true);assert.equal(writes[0].ray5.host,'YOUR_RAY5_IP');
    assert.deepEqual(writes[0].camera.deskew.output_size,[1200,1200]);
    failSave=true;await page.locator('#savePts').click();await page.waitForFunction(()=>document.getElementById('msg').textContent.includes('Fixture save failed'));assert(await page.locator('#savePts').isEnabled());failSave=false;
    await page.locator('#resetPts').click();assert.equal(await page.locator('#ov circle').count(),0);assert.equal(config.camera.deskew.source_points.length,4,'Reset only clears draft');
    const beforeReads=rawReads;await page.locator('#reloadImg').click();await page.waitForFunction(()=>document.getElementById('calImg').complete);assert(rawReads>beforeReads);
    await page.locator('#takeSnap').click();await page.waitForFunction(()=>!document.getElementById('takeSnap').disabled);assert.equal(captures,1);
    failCapture=true;await page.locator('#takeSnap').click();await page.waitForFunction(()=>document.getElementById('msg').textContent.includes('Fixture camera offline'));assert(await page.locator('#takeSnap').isEnabled());failCapture=false;
    failImage=true;await page.locator('#reloadImg').click();await page.waitForFunction(()=>document.getElementById('msg').textContent.includes('No latest_raw.jpg'));assert(await page.locator('#calibrationEmpty').isVisible());failImage=false;
    await page.locator('#reloadImg').click();await readyImage();

    await page.goto(base+'/camera-calibration');await readyImage();assert(await page.locator('.camera-tool-page header').isVisible());
    await page.goto(base+'/embed');const frame=page.frameLocator('iframe');await frame.locator('#calImg').waitFor();
    await page.waitForFunction(()=>document.querySelector('iframe').contentDocument.body.classList.contains('camera-tools-embedded'));
    assert(!(await frame.locator('header').isVisible()));assert(!(await frame.locator('.camera-return-link').isVisible()));
    await page.setViewportSize({width:375,height:1000});await assertNoOverflow(375);
    await page.screenshot({path:path.join(output,'calibration-embedded.png'),fullPage:true});
    failConfig=true;await page.goto(base+'/camera/calibration');await page.waitForFunction(()=>document.getElementById('msg').textContent.includes('Fixture config unavailable'));assert(await page.locator('#calibrationEmpty').isVisible());
    assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
    const report={passed:true,routes:['/camera/popout','/camera/calibration','/camera-calibration'],embeddedChecked:true,widths:[1280,768,375,320],fixtureSaveRequests:writes.length,fixtureCaptures:captures,streams,runtimeErrors:errors,realMachineCommands:0,realConfigWrites:0,screenshots:output};
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
  }finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);process.exitCode=1;server.closeAllConnections();server.close();});

/* Opt-in hardware smoke test. Never applies settings, resets, or moves the machine. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

if (process.env.RAY5_LIVE_READONLY_TEST !== '1') {
  throw new Error('Set RAY5_LIVE_READONLY_TEST=1 to explicitly enable real-machine reads.');
}
const base = 'http://127.0.0.1:5050';
const output = path.resolve(__dirname, '../build/firmware-pages-live-readonly');
fs.mkdirSync(output, {recursive:true});
const report = {passed:false, started:new Date().toISOString(), requests:[], blocked:[], errors:[], httpErrors:[],issues:[]};
const allowedGet = new Set([
  '/api/status/live', '/api/machine-settings/collect/status', '/api/esp32/info',
  '/api/esp32/eeprom', '/api/esp32/eeprom/backups', '/api/esp32/eeprom/compare',
]);
const digestSettings = rows => rows.map(row => [row.path || row.key, String(row.raw_value ?? row.value ?? '')])
  .sort((a,b) => a[0].localeCompare(b[0]));

(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.PLAYWRIGHT_CHROMIUM ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM} : {})});
  const context = await browser.newContext({viewport:{width:1280,height:1000},acceptDownloads:true});
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), method = request.method();
    const local = url.origin === base;
    const allowed = local && (
      (method === 'GET' && (!url.pathname.startsWith('/api/') || allowedGet.has(url.pathname) ||
        /^\/api\/esp32\/eeprom\/backups\/[^/]+(?:\/download)?$/.test(url.pathname))) ||
      (method === 'POST' && url.pathname === '/api/machine-settings/collect') ||
      (method === 'POST' && url.pathname === '/api/esp32/command' && request.postDataJSON()?.command === '?')
    );
    if (!allowed) {
      report.blocked.push({method,path:url.pathname});
      return route.abort('blockedbyclient');
    }
    if (url.pathname.startsWith('/api/')) report.requests.push({method,path:url.pathname});
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 400) report.httpErrors.push({path:new URL(response.url()).pathname,status:response.status()});
  });
  page.on('dialog', dialog => dialog.dismiss());
  const readStatus = () => page.evaluate(async () => {
    const response = await fetch('/api/status/live');
    const data = await response.json();
    return {connected:data.websocket_connected,raw:data.last_raw_status,age:data.last_status_age_seconds};
  });
  try {
    await page.goto(base+'/machine-settings');
    report.before = await readStatus();
    assert(report.before.connected && report.before.age < 5 && /^<Idle\|/.test(report.before.raw), 'Machine must be freshly idle');
    await page.waitForFunction(() => settingsReady && !busy(), null, {timeout:90000});
    const grblBefore = await page.evaluate(() => settingsRows.map(row => ({key:row.key,value:row.value})));
    assert(grblBefore.length >= 20, 'Expected actual GRBL settings');
    if(process.env.RAY5_EXPECTED_GRBL_COUNT) assert.equal(grblBefore.length,Number(process.env.RAY5_EXPECTED_GRBL_COUNT));
    report.grbl = {settings:grblBefore.length,firmware:await page.locator('#gvFirmwareVersion').textContent(),categories:[]};
    assert(await page.locator('#msSave').isDisabled());
    assert(await page.locator('#msApply').isDisabled());
    await page.locator('#msVersionCard').evaluate(el => el.open = true);
    assert((await page.locator('#gvMachine').textContent()).trim().length > 0);
    await page.screenshot({path:path.join(output,'grbl-live-desktop.png'),fullPage:true});
    for (const category of ['motion','homing','laser','controller','all','diagnostics']) {
      await page.locator(`[data-category="${category}"]`).click();
      report.grbl.categories.push(category);
    }
    assert(/\$\d+=/.test(await page.locator('#msRaw').textContent()));
    assert((await page.locator('#msVersionRaw').textContent()).includes('[VER:'));
    await page.locator('[data-category="all"]').click();
    await page.locator('#msSearch').fill('$110');
    assert.equal(await page.locator('#msValue_110').count(),1);
    await page.locator('#msSearch').fill('');
    await page.locator('#msShowZ').check();
    await page.locator('#msChangedOnly').check();
    assert.equal(await page.locator('.grbl-setting-row').count(),0);
    await page.locator('#msChangedOnly').uncheck();
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#msDownload').click();
    const backup = await downloadPromise;
    const backupText = fs.readFileSync(await backup.path(),'utf8');
    assert(backupText.includes('$110='));
    report.grbl.backupDownload = true;
    report.grbl.repeatReads=[];
    const repeats=Math.max(1,Math.min(20,Number(process.env.RAY5_GRBL_READ_REPEATS||1)));
    for(let index=0;index<repeats;index++){
      const started=Date.now();
      await page.locator('#msRefresh').click();
      await page.waitForFunction(() => settingsReady && !busy(), null, {timeout:90000});
      const grblAfter = await page.evaluate(() => settingsRows.map(row => ({key:row.key,value:row.value})));
      assert.deepEqual(digestSettings(grblBefore),digestSettings(grblAfter));
      report.grbl.repeatReads.push({index:index+1,settings:grblAfter.length,milliseconds:Date.now()-started});
    }
    report.grbl.unchangedAfterFreshRead = true;
    await page.setViewportSize({width:375,height:950});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1));
    await page.screenshot({path:path.join(output,'grbl-live-mobile.png'),fullPage:true});

    await page.setViewportSize({width:1280,height:1000});
    await page.goto(base+'/esp32');
    await page.waitForFunction(() => eepromReady && !espBusy, null, {timeout:90000});
    const espBefore = await page.evaluate(async () => (await (await fetch('/api/esp32/eeprom')).json()).settings);
    assert(espBefore.length > 0);
    report.esp32 = {settings:espBefore.length,categories:[],info:await page.evaluate(() => ({
      ok:deviceInfo.ok,firmware:deviceInfo.fw_version,hardware:deviceInfo.fw_hw,
      host:deviceInfo.http_host,port:deviceInfo.http_port,
    }))};
    assert(report.esp32.info.ok);
    assert(await page.locator('#saveChanges').isDisabled());
    assert(await page.locator('#espApply').isDisabled());
    assert(await page.locator('#sendGcode').isDisabled());
    assert(await page.locator('#sendEsp').isDisabled());
    await page.screenshot({path:path.join(output,'esp32-live-desktop.png'),fullPage:true});
    for (const section of ['overview','network','services','hardware','backups','advanced']) {
      await page.locator(`[data-section="${section}"]`).click();
      report.esp32.categories.push(section);
      const ids = await page.locator('[id]').evaluateAll(els => els.map(el => el.id));
      assert.equal(ids.length,new Set(ids).size,'Duplicate EEPROM field IDs');
      assert(await page.evaluate(() => {
        const text=document.body.textContent;
        return Array.from(secretValues).every(value => !value || !text.includes(value));
      }), 'Secret exposed in page text');
    }
    const firstPath = espBefore[0].path;
    await page.locator('#eepromFilter').fill(firstPath);
    assert(await page.locator('.esp-field-wrap').count() > 0);
    await page.locator('#eepromFilter').fill('');
    await page.locator('#refreshInfo').click();
    await page.waitForFunction(() => !espBusy);
    await page.locator('#refreshWs').click();
    await page.waitForFunction(() => !espBusy);
    await page.locator('#espCommandsEnabled').check();
    await page.locator('#gcodeCmd').fill('?');
    const statusReply = page.waitForResponse(response => new URL(response.url()).pathname === '/api/esp32/command');
    await page.locator('#sendGcode').click();
    const statusData = await (await statusReply).json();
    await page.waitForFunction(() => !espBusy);
    report.esp32.readonlyStatusCommand = (await page.locator('#msg').textContent()).includes('accepted');
    if (report.esp32.readonlyStatusCommand) {
      assert(statusData.ok && statusData.result.synthetic === false);
      assert(['websocket','http'].includes(statusData.result.source));
      assert(/^<Idle\|/.test(statusData.result.raw));
      report.esp32.statusQueryResult = {source:statusData.result.source,raw:statusData.result.raw,synthetic:statusData.result.synthetic};
    }
    if (!report.esp32.readonlyStatusCommand) report.issues.push({
      feature:'ESP32 Advanced Tools: manual GRBL status query',
      message:await page.locator('#msg').textContent(),
      liveStatus:await readStatus(),
    });
    await page.locator('#espCommandsEnabled').uncheck();
    await page.locator('[data-section="backups"]').click();
    if (await page.locator('#backupSelect option').count()) {
      await page.locator('#loadBackup').click();
      await page.waitForFunction(() => !espBusy);
      assert((await page.locator('#backupView').textContent()).length > 0);
      await page.locator('#compareBackup').click();
      await page.waitForFunction(() => !espBusy);
      assert((await page.locator('#msg').textContent()).includes('Read-only comparison complete'));
      report.esp32.existingBackupViewAndCompare = true;
    } else report.esp32.existingBackupViewAndCompare = 'Skipped: no saved backups';
    await page.locator('[data-section="advanced"]').click();
    await page.locator('#refreshEeprom').click();
    await page.waitForFunction(() => eepromReady && !espBusy, null, {timeout:90000});
    const espAfter = await page.evaluate(async () => (await (await fetch('/api/esp32/eeprom')).json()).settings);
    assert.deepEqual(digestSettings(espBefore),digestSettings(espAfter));
    report.esp32.unchangedAfterFreshRead = true;
    await page.locator('[data-section="network"]').click();
    await page.setViewportSize({width:375,height:950});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1));
    await page.screenshot({path:path.join(output,'esp32-live-mobile.png'),fullPage:true});
    report.after = await readStatus();
    assert(report.after.connected && report.after.age < 5 && /^<Idle\|/.test(report.after.raw));
    assert.deepEqual(report.errors,[]);
    assert(report.httpErrors.every(item => item.path === '/api/esp32/command' && item.status === 503), 'Unexpected HTTP errors');
    assert.deepEqual(report.blocked,[]);
    report.completed=true;
    report.passed=report.issues.length === 0;
    if (!report.passed) process.exitCode=1;
  } catch (error) {
    report.failure=error.message;
    process.exitCode=1;
  } finally {
    report.finished=new Date().toISOString();
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
    await browser.close();
  }
})();

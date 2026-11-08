/* Test dashboard read scheduling without DOM, HTTP, or machine access. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../web/static/app.js'),'utf8').split('function fmtPos')[0];
let calls=[], timers=new Map(), nextTimer=0, warnings=[];
const context = vm.createContext({AbortController, Map, Promise,
  console:{warn:(...args)=>warnings.push(args)},
  setTimeout:callback=>{timers.set(++nextTimer,callback);return nextTimer;},
  clearTimeout:key=>timers.delete(key),
  fetch:(url,options)=>new Promise((resolve,reject)=>{
    calls.push({url,options,resolve:body=>resolve({json:async()=>body}),reject});
    options.signal?.addEventListener('abort',()=>reject(new Error('Read timeout')));
  }),
});
vm.runInContext(source,context);
(async()=>{
  const reads=[context.api('/api/status'),context.api('/api/status'),context.api('/api/status')];
  assert.equal(calls.length,1);calls[0].resolve({ok:true});await Promise.all(reads);assert.equal(timers.size,0);
  const fresh=context.api('/api/status');assert.equal(calls.length,2);calls[1].resolve({ok:true});await fresh;
  const writes=[context.api('/api/stop','POST',{}),context.api('/api/stop','POST',{})];
  assert.equal(calls.length,4);assert(!calls[2].options.signal);calls[2].resolve({ok:true});calls[3].resolve({ok:true});await Promise.all(writes);
  const failed=context.api('/api/jobs');calls.at(-1).reject(new Error('offline'));await assert.rejects(failed,/offline/);
  const retry=context.api('/api/jobs');calls.at(-1).resolve({ok:true});await retry;
  const timeout=context.api('/api/console');const expire=Array.from(timers.values()).at(-1);expire();await assert.rejects(timeout,/timeout/);assert.equal(timers.size,0);
  await context.pollDashboard(()=>Promise.reject(new Error('offline')));assert.equal(warnings.length,1);
  console.log('PASS: coalesced reads, fresh retries, bounded timeouts, independent writes, handled polling errors');
})().catch(error=>{console.error(error);process.exitCode=1;});

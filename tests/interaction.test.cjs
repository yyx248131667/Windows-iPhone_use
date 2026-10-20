const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let source = fs.readFileSync('web/index.html', 'utf8').split('<script>')[1].split('</script>')[0];
source = source.slice(0, source.indexOf('    // Polling Loops'));
const elements = new Map();
const handlers = new Map();
let requests = [], completions = [];
const ctx = vm.createContext({ console, performance, URL, Blob, setTimeout, clearTimeout,
 document: { hidden: false, getElementById(id) {
   if (!elements.has(id)) elements.set(id, { style: {}, addEventListener(name, fn) { handlers.set(name, fn); }, removeAttribute() {}, getBoundingClientRect() { return {left:0,top:0,width:430,height:932}; } });
   return elements.get(id);
 }},
 fetch(url, options) { requests.push({url, options}); return new Promise(resolve => completions.push(resolve)); }
});
vm.runInContext(source, ctx);
(async () => {
 const fit = vm.runInContext('fittedRect({left:0,top:0,width:400,height:400},100,200)',ctx);
 assert.equal(fit.left,100); assert.equal(fit.width,200); assert.equal(fit.height,400);
 const a = vm.runInContext('actionRequest("/tap1", {x:1})',ctx);
 const b = vm.runInContext('actionRequest("/tap2", {x:2})',ctx);
 assert.equal(requests.length,1,'second click must wait rather than run concurrently or disappear');
 completions.shift()({ok:true,json:async()=>({success:true})});
 await a; await new Promise(resolve=>setImmediate(resolve));
 assert.equal(requests.length,2); assert.equal(requests[1].url,'/tap2');
 completions.shift()({ok:true,json:async()=>({success:true})}); await b;
 assert.equal(vm.runInContext('actionInFlight',ctx),false);
 const c = vm.runInContext('actionRequest("/fail")',ctx);
 const d = vm.runInContext('actionRequest("/stale")',ctx);
 completions.shift()({ok:false,json:async()=>({detail:'failed'})});
 assert.equal(await c,false); assert.equal(await d,false);
 assert.equal(requests.length,3,'stale queued action must not execute after failure');
 vm.runInContext('wdaOnline = true; airplayActive = true',ctx);
 const wheel = handlers.get('wheel');
 const event = {clientX:215,clientY:400,deltaY:100,deltaX:0,deltaMode:0,preventDefault(){}};
 wheel(event); wheel(event); wheel(event);
 assert.equal(requests.length,4,'one wheel burst must produce only one swipe');
 completions.shift()({ok:true,json:async()=>({success:true})});
 await new Promise(resolve=>setImmediate(resolve));
 wheel(event);
 assert.equal(requests.length,4,'momentum after completion must not cause another swipe');
 console.log('Coordinate mapping and queued interaction checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

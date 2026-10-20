const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
let source = fs.readFileSync('web/index.html', 'utf8').split('<script>')[1].split('</script>')[0];
source = source.slice(0, source.indexOf('    // Polling Loops'));
let resolveFrame, calls = 0;
const elements = new Map();
const context = vm.createContext({
  console, URL, Blob, performance, setTimeout, clearTimeout,
  document: { hidden: false, getElementById(id) {
    if (!elements.has(id)) elements.set(id, { style: {}, addEventListener() {}, removeAttribute() {} });
    return elements.get(id);
  }},
  Image: class { async decode() {} },
  fetch: () => { calls++; return new Promise(resolve => { resolveFrame = resolve; }); }
});
vm.runInContext(source, context);
(async () => {
  vm.runInContext('wdaOnline = true', context);
  const first = vm.runInContext('fetchScreen()', context);
  await vm.runInContext('fetchScreen()', context);
  assert.equal(calls, 1, 'overlapping screenshots must be skipped');
  resolveFrame({ ok: true, blob: async () => new Blob(['jpeg']) });
  await first;
  assert.equal(vm.runInContext('screenInFlight', context), false);
  vm.runInContext('actionInFlight = true', context);
  await vm.runInContext('fetchScreen()', context);
  assert.equal(calls, 1, 'screenshots must not compete with user actions');
  vm.runInContext('actionInFlight = false; airplayState.streaming = true', context);
  vm.runInContext('displayMode = "auto"; setAirPlayActive(true)', context);
  await vm.runInContext('fetchScreen()', context);
  assert.equal(calls, 1, 'AirPlay must suspend WDA screenshots');
  vm.runInContext('airplayStreamFailed()', context);
  assert.equal(vm.runInContext('airplayActive', context), false, 'stream failure must enable fallback');
  vm.runInContext('airplayRetryAfter = 0; usbState.streaming = true; selectStream()', context);
  assert.equal(vm.runInContext('streamSource', context), 'usb', 'automatic mode must prefer USB');
  assert.match(elements.get('airplay-img').src, /\/api\/usb\/stream/);
  vm.runInContext('usbState.streaming = false; selectStream()', context);
  assert.equal(vm.runInContext('streamSource', context), 'airplay', 'USB loss must fall back to AirPlay');
  vm.runInContext('displayMode = "usb"; selectStream()', context);
  assert.equal(vm.runInContext('airplayActive', context), false, 'explicit USB must not silently select AirPlay');
  console.log('WebUI concurrency and AirPlay fallback checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });

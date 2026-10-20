# Experimental WDA direct touch build

GitHub Actions builds upstream WDA revision `3d6a4e03cdd673e540289c610f7e189f8ffea434`
with a narrow patch to `FBTouchActionCommands.m`. The build runs on macOS with
Xcode 26.2, uses Release configuration, and produces an unsigned IPA plus full
test products. No signing credentials or pairing records are uploaded.

The new `POST /session/{sessionId}/wda/fastTap` route accepts numeric `x`, `y`,
`width`, `height`, and `orientation=1`. Coordinates use iPhone points. This
experimental route supports the main display in portrait only; the caller must
verify the actual orientation before using it. It constructs a 20 ms touch
directly, avoiding W3C parsing and application coordinate/snapshot resolution.
The completion wait uses a 5 ms run-loop interval instead of changing WDA's
global spinner. It still waits for XCTest's synthesis completion callback and
checks its success flag. A timeout is an uncertain outcome and must not be
automatically retried.

The response includes `completed`, `prepare_ms`, `synthesis_ms`,
`completion_wait_ms`, and `total_ms` (timings nested under `timing`). These
measure the route and XCTest callback, not the time at which a user sees the
resulting frame. Reaching 300 ms is an experimental goal, not a promise.

The workflow leaves the existing Windows installation untouched. The IPA must
be signed locally and installed as a test runner before the endpoint can be
measured. The full test-products ZIP preserves the original XCTest frameworks;
the convenience IPA omits the top-level XC frameworks to use the device's
system XCTest, matching the working Windows installation strategy. All
dependencies must still be signed correctly by the local signer.

After installing the candidate and starting its WDA session, return to a harmless
portrait Home screen and explicitly choose a safe point, for example the clock
area of the status bar. Then run:

```powershell
.\.venv\Scripts\python.exe tools/benchmark_fast_touch.py --x 215 --y 28
```

The tool alternates five confirmed fast taps and five standard actions, reports
HTTP round-trip times, and saves detailed measurements in the ignored
`artifacts/fast-touch-benchmark.json`. It stops on errors without replaying an
uncertain action. Verify the coordinates are harmless on your own device.

Upstream WDA: <https://github.com/appium/WebDriverAgent>. The artifact includes
its upstream license and the complete applied patch.

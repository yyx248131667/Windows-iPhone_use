// Experimental WDA route. Real synthesis completion is required before success.
+ (id<FBResponsePayload>)handleFastTap:(FBRouteRequest *)request
{
  NSTimeInterval started = NSProcessInfo.processInfo.systemUptime;
  NSDictionary *args = request.arguments;
  for (NSString *key in @[@"x", @"y", @"width", @"height", @"orientation"]) {
    if (![args[key] isKindOfClass:NSNumber.class] || !isfinite([args[key] doubleValue])) {
      return FBResponseWithStatus([FBCommandStatus invalidArgumentErrorWithMessage:
        [NSString stringWithFormat:@"%@ must be a finite number", key] traceback:nil]);
    }
  }
  double x = [args[@"x"] doubleValue], y = [args[@"y"] doubleValue];
  double width = [args[@"width"] doubleValue], height = [args[@"height"] doubleValue];
  NSInteger orientation = [args[@"orientation"] integerValue];
  // Initially limited to portrait: never guess a rotated viewport's coordinates.
  if (orientation != UIInterfaceOrientationPortrait || width <= 0 || height <= 0 ||
      width > height || x < 0 || y < 0 || x >= width || y >= height) {
    return FBResponseWithStatus([FBCommandStatus invalidArgumentErrorWithMessage:
      @"fastTap requires portrait viewport dimensions and an in-bounds point" traceback:nil]);
  }
  XCPointerEventPath *path = [[XCPointerEventPath alloc] initForTouchAtPoint:CGPointMake(x, y) offset:0];
  [path liftUpAtOffset:0.02];
  XCSynthesizedEventRecord *record;
  if ([XCSynthesizedEventRecord instancesRespondToSelector:@selector(initWithName:displayID:interfaceOrientation:)]) {
    record = [[XCSynthesizedEventRecord alloc] initWithName:@"WDA Fast Tap"
      displayID:XCUIScreen.mainScreen.displayID interfaceOrientation:orientation];
  } else {
    record = [[XCSynthesizedEventRecord alloc] initWithName:@"WDA Fast Tap" interfaceOrientation:orientation];
  }
  [record addPointerEventPath:path];
  NSTimeInterval submitted = NSProcessInfo.processInfo.systemUptime;
  __block atomic_bool finished = false;
  __block NSError *synthesisError = nil;
  __block BOOL succeeded = NO;
  __block NSTimeInterval callbackAt = 0;
  [[XCUIDevice.sharedDevice eventSynthesizer] synthesizeEvent:record completion:^(BOOL result, NSError *error) {
    synthesisError = error;
    succeeded = result;
    callbackAt = NSProcessInfo.processInfo.systemUptime;
    atomic_store_explicit(&finished, true, memory_order_release);
  }];
  NSError *waitError = nil;
  BOOL completed = [[[[FBRunLoopSpinner new] interval:0.005] timeout:10]
    spinUntilTrue:^BOOL{ return atomic_load_explicit(&finished, memory_order_acquire); } error:&waitError];
  if (!completed) {
    return FBResponseWithUnknownErrorFormat(@"Touch completion timed out; outcome uncertain. Do not replay automatically.");
  }
  if (synthesisError != nil) {
    return FBResponseWithUnknownError(synthesisError);
  }
  if (!succeeded) {
    return FBResponseWithUnknownErrorFormat(@"XCTest did not confirm touch synthesis success");
  }
  NSTimeInterval ended = NSProcessInfo.processInfo.systemUptime;
  return FBResponseWithObject(@{@"completed": @YES, @"implementation": @"direct-touch-v1",
    @"timing": @{@"prepare_ms": @((submitted - started) * 1000),
      @"synthesis_ms": @((callbackAt - submitted) * 1000),
      @"completion_wait_ms": @((ended - callbackAt) * 1000),
      @"total_ms": @((ended - started) * 1000)}});
}

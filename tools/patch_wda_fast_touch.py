"""Apply a narrow experimental route to the pinned upstream WDA source."""
import argparse
from pathlib import Path

WDA_REVISION = "3d6a4e03cdd673e540289c610f7e189f8ffea434"


def patch(root):
    target = Path(root) / "WebDriverAgentLib/Commands/FBTouchActionCommands.m"
    source = target.read_text(encoding="utf-8")
    if "handleFastTap:" in source:
        raise ValueError("fast touch patch is already present")
    imports = '\n'.join(f'#import "{name}"' for name in [
        "FBCommandStatus.h", "FBRunLoopSpinner.h", "XCUIDevice.h", "XCUIScreen.h",
        "XCPointerEventPath.h", "XCSynthesizedEventRecord.h"])
    source = source.replace('#import "FBSession.h"', '#import "FBSession.h"\n' + imports +
                            '\n#import <stdatomic.h>\n#import <math.h>', 1)
    anchor = '    [[FBRoute POST:@"/actions"] respondWithTarget:self action:@selector(handlePerformW3CTouchActions:)],'
    if source.count(anchor) != 1 or source.count("\n@end") != 1:
        raise ValueError("upstream route layout changed; review patch before building")
    source = source.replace(anchor, anchor + '\n    [[FBRoute POST:@"/wda/fastTap"] respondWithTarget:self action:@selector(handleFastTap:)],', 1)
    handler = Path(__file__).with_name("wda_fast_touch.m.inc").read_text(encoding="utf-8")
    source = source.replace("\n@end", "\n" + handler + "\n@end", 1)
    target.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    patch(parser.parse_args().source)

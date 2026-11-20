"""Board-portion driver for tests/lib/test_board_portions:
runs in a subprocess with WB_VIEWER_CONFIG pointed at the
test's fixture config, computes the board portions and
the todos feed through the server package, and writes
them as one JSON document.

Usage: board_driver.py <out.json>
"""

import json
import sys
from pathlib import Path

from server import feeds
from server.common import get_sweep


def main() -> int:
    sweep = get_sweep()
    alpha = sweep.by_slug("alpha")
    beta = sweep.by_slug("beta")
    out = {
        "alpha_board": feeds.board_project_feed(alpha),
        "alpha_board_offset50": feeds.board_project_feed(
            alpha, {"done_offset": "50"}),
        "alpha_board_limit5": feeds.board_project_feed(
            alpha, {"done_limit": "5"}),
        "alpha_board_junk": feeds.board_project_feed(
            alpha, {"done_offset": "-3",
                    "done_limit": "abc"}),
        "beta_board": feeds.board_project_feed(beta),
        "alpha_todos": feeds.todos_feed(alpha),
        "board_functions": sorted(
            name for name in dir(feeds)
            if "board" in name
            and not name.startswith("_")),
    }
    Path(sys.argv[1]).write_text(
        json.dumps(out, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

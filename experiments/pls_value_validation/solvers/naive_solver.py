#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    challenge = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    answers = [{"id": case["id"], "key": "A"} for case in challenge["hidden_cases"]]
    Path(sys.argv[2]).write_text(json.dumps({"answers": answers}), encoding="utf-8")


if __name__ == "__main__":
    main()

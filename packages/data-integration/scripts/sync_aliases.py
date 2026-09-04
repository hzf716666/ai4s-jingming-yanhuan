# -*- coding: utf-8 -*-
"""把人工确认的 schema 候选回写 indicator_dict.json(别名自生长)。

输入格式(与 schema_match_candidates.json 同构, entries 需带 "confirmed": true):
    [
      {"raw": "营业收入（千元）", "candidate": "营业收入", "confidence": 0.95,
       "reason": "...", "evidence_count": 3, "confirmed": true},
      ...
    ]
用法:
    python scripts/sync_aliases.py <candidates.json>            # 回写字典(幂等)
    python scripts/sync_aliases.py --dry-run <candidates.json>  # 仅预览
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
DICT = PKG / "data" / "indicator_dict.json"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        print(__doc__)
        return 1
    candidates_path = Path(args[0])
    if not candidates_path.exists():
        print(f"candidates not found: {candidates_path}")
        return 1

    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        print("invalid candidates format")
        return 1

    conf = [i for i in items if isinstance(i, dict) and i.get("confirmed") is True]
    if not conf:
        print("no confirmed entries — candidates must carry 'confirmed': true")
        return 1

    d = json.loads(DICT.read_text(encoding="utf-8"))
    by_title = {ind["title"]: ind for ind in d.get("indicators", [])}
    added = dropped = 0
    for c in conf:
        title = c.get("candidate")
        raw = str(c.get("raw") or "")
        if not title or not raw or title not in by_title:
            dropped += 1
            continue
        ind = by_title[title]
        aliases = ind.setdefault("aliases", [])
        if raw in aliases or raw == title:
            dropped += 1
            continue
        if dry:
            print(f"  + alias '{raw}' -> '{title}'")
        else:
            aliases.append(raw)
        added += 1

    if not dry and added:
        DICT.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"added={added} dropped={dropped} dry_run={dry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

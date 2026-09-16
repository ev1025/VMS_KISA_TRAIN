# -*- coding: utf-8 -*-
"""문서 안의 상대 링크와 문서명 언급이 실제로 존재하는지 본다. 통폐합하면 깨지기 쉽다."""
import re
from pathlib import Path

V = Path(__file__).resolve().parents[1]
DOCS = sorted(list((V / "docs").rglob("*.md")) + [V / "CLAUDE.md"])
bad = 0
for f in DOCS:
    t = f.read_text(encoding="utf-8")
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", t):
        tgt = m.group(2)
        if tgt.startswith(("http", "#")):
            continue
        q = (f.parent / tgt).resolve()
        if not q.exists():
            print(f"  깨진 링크  {f.relative_to(V)}  ->  {tgt}"); bad += 1
    for m in re.finditer(r"`(docs/[\w/가-힣_]+\.md)`", t):
        if not (V / m.group(1)).exists():
            print(f"  없는 문서  {f.relative_to(V)}  ->  {m.group(1)}"); bad += 1
print(f"  {'깨진 곳 없음' if not bad else str(bad) + '건'}")

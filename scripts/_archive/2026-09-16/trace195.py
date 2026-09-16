# -*- coding: utf-8 -*-
"""한 편의 방화 판정을 표본 단위로 따라간다. 왜 그 시각에 울렸는지 보려는 용도."""
import json
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

C = K.ITEMS["fire"]
stem = sys.argv[1]
lo, hi = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0.0, 1e9)
d = json.load(open(V / "dumps/score_tl/_deploy.json", encoding="utf-8"))[stem]
gt, rows = d["gt"], d["rows"]

print(f"{stem}  GT {gt}s · 정검 창 [{gt-2}, {gt+10}]")
print(f"규칙: 불 >= {C['fire']} 가 {C['win']}표본(={C['win']*C['stride']}초) 창에 {C['hits']}회 → 창의 첫 적중 + 지연 {C['delay']}초")
print()
q = deque(maxlen=C["win"])
fired = None
print(f"{'t':>7}{'불':>7}{'연기':>7}{'적중':>5}{'창내':>5}")
for t, f, s in rows:
    hit = f >= C["fire"] or (f >= 0.3 and s >= C["smoke"])
    q.append((t, hit))
    n = sum(1 for _, x in q if x)
    mark = ""
    if fired is None and n >= C["hits"]:
        fired = next(t0 for t0, x in q if x)
        mark = f"   <== 성립. 창 첫 적중 {fired}s  →  SA {fired + C['delay']}s"
    if lo <= t <= hi:
        print(f"{t:>7.1f}{f:>7.3f}{s:>7.3f}{('O' if hit else '.'):>5}{n:>5}{mark}")
    elif mark:
        print(f"{t:>7.1f}{f:>7.3f}{s:>7.3f}{('O' if hit else '.'):>5}{n:>5}{mark}")

print()
sa = None if fired is None else fired + C["delay"]
ok = sa is not None and gt - 2 <= sa <= gt + 10
print(f"SA = {sa}  →  {'정검' if ok else '오검/미검'}   (창 상한 {gt+10}, 여유 {None if sa is None else round(gt+10-sa,1)}초)")
top = sorted(((f, t) for t, f, s in rows), reverse=True)[:10]
print("클립 전체 불 신뢰도 상위 10:", [(round(t, 1), round(f, 3)) for f, t in top])

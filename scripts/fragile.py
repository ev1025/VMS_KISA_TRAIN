# -*- coding: utf-8 -*-
"""표본 하나를 빼면 판정이 어떻게 되나. 방화 판정이 몇 개의 표본에 매달려 있는지 본다."""
import json
import sys
from collections import deque
from pathlib import Path

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

C = K.ITEMS["fire"]
D = json.load(open(V / "dumps/score_tl/_deploy.json", encoding="utf-8"))


def sa_of(rows):
    q = deque(maxlen=C["win"])
    for t, f, s in rows:
        q.append((t, f >= C["fire"] or (f >= 0.3 and s >= C["smoke"])))
        if sum(1 for _, x in q if x) >= C["hits"]:
            return next(t0 for t0, x in q if x) + C["delay"]
    return None


def ok(sa, gt):
    return sa is not None and gt - 2 <= sa <= gt + 10


print(f"{'클립':<16}{'GT':>5}{'SA':>8}{'판정':>6}{'여유':>7}{'쪽':>8}   한 표본만 빼도 깨지는 표본")
for stem in sorted(D):
    e = D[stem]; gt = e["gt"]; rows = e["rows"]
    sa = sa_of(rows)
    base = ok(sa, gt)
    if not base:
        print(f"{stem:<16}{gt:>5}{str(sa):>8}{'미검/오검':>6}")
        continue
    killers = []
    for i, (t, f, s) in enumerate(rows):
        if f < C["fire"]:
            continue                       # 적중이 아닌 표본은 빼도 아무 일 없다
        cut = rows[:i] + rows[i + 1:]
        if not ok(sa_of(cut), gt):
            killers.append(round(t, 1))
    late = round(gt + 10 - sa, 1)       # 창 상한(GT+10)까지 남은 여유
    early = round(sa - (gt - 2), 1)     # 창 하한(GT-2)까지 남은 여유
    marg = min(late, early)
    print(f"{stem:<16}{gt:>5}{sa:>8.1f}{'정검':>6}{marg:>6.1f}s{('늦어서' if late < early else '일러서'):>8}   "
          f"{len(killers)}개 {killers if killers else ''}")

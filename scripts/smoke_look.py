# -*- coding: utf-8 -*-
"""연기 채널이 실제로 쓸 만한 신호인지 배포 덤프 10편으로 본다.

보는 것
  - 불이 언제 처음 0.40 을 넘나 (지금 규칙이 터지는 근거)
  - 연기는 GT 이전에 이미 높은가 (그러면 문턱으로는 못 가른다)
  - 연기만으로 판정하면 창 안에 들어오나
"""
import json
import sys
from pathlib import Path

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

C = K.ITEMS["fire"]
d = json.load(open(V / "dumps/score_tl/_deploy.json", encoding="utf-8"))

print("배포 앙상블 덤프 10편")
print(f"{'클립':<16}{'GT':>6}{'불>=0.40':>10}{'연기최고':>9}{'GT전 연기최고':>14}{'앞60초 연기중앙':>16}")
for stem in sorted(d):
    e = d[stem]; gt = e["gt"]; rows = e["rows"]
    f40 = next((r[0] for r in rows if r[1] >= C["fire"]), None)
    smax = max(r[2] for r in rows)
    spre = max([r[2] for r in rows if r[0] < gt - 2] or [0.0])
    head = sorted(r[2] for r in rows if r[0] <= 60)
    smed = head[len(head) // 2] if head else 0.0
    print(f"{stem:<16}{gt:>6}{('-' if f40 is None else f'{f40:.1f}'):>10}"
          f"{smax:>9.3f}{spre:>14.3f}{smed:>16.3f}")

print()
print("연기만으로 판정하면 (창 20 · 3회 · 지연 10 · 문턱을 훑어서)")
print(f"{'문턱':>6}{'점수':>8}{'정검':>6}{'미검':>6}{'오검':>6}")
for th in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
    pairs = []
    for stem, e in d.items():
        gt = e["gt"]
        from collections import deque
        q = deque(maxlen=C["win"]); sa = None
        for t, f, s in e["rows"]:
            q.append((t, s >= th))
            if sum(1 for _, x in q if x) >= C["hits"]:
                sa = next(t0 for t0, x in q if x) + C["delay"]; break
        pairs.append(([{"start_s": gt, "desc": "F"}],
                      [{"start_s": sa, "desc": "F"}] if sa is not None else []))
    r = K.score(pairs)
    print(f"{th:>6.2f}{r['점수']:>8.2f}{r['정상검출']:>6}{r['미검출']:>6}{r['오검출']:>6}")

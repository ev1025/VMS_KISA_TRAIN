# -*- coding: utf-8 -*-
"""앙상블에 모델을 더했는데 왜 점수가 떨어지나. C00_089_0001 을 표본 단위로 본다."""
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import fire_ens_try as E   # noqa: E402

FOG, SMALL = E.DEPLOY["fire_fog.pt"], E.DEPLOY["fire_small.pt"]
NEW = "f1280_best_s_20260915"
TL = V / "dumps/score_tl"

for label, names in (("배포 2벌", [FOG, SMALL]), ("3벌(+f1280)", [FOG, SMALL, NEW])):
    d = E.merge(names)
    print(f"--- {label}")
    for stem in ("C00_089_0001", "C00_195_0001", "C00_216_0003"):
        e = d[stem]; gt = e["gt"]; sa = E.judge(e["rows"])
        ok = sa is not None and gt - 2 <= sa <= gt + 10
        print(f"    {stem}  GT {gt}  창 [{gt-2}, {gt+10}]  SA {sa}  {'정검' if ok else '오검+미검'}")
print()


def col(name, stem):
    return {round(r[0], 2): r[1] for r in
            json.loads((TL / (name + ".json")).read_text(encoding="utf-8"))[stem]["rows"]}


stem = "C00_089_0001"
b, s, n = col(FOG, stem), col(SMALL, stem), col(NEW, stem)
print(f"{stem}  GT 218 · 창 [216, 228] · 불 문턱 {E.C['fire']}")
print("    시각    fog  small  f1280  배포max  3벌max")
for t in sorted(b):
    if not (195 <= t <= 212):
        continue
    x, y, z = b.get(t, 0.0), s.get(t, 0.0), n.get(t, 0.0)
    d2, d3 = max(x, y), max(x, y, z)
    if max(d2, d3) < 0.25:
        continue
    flag = "   <-- 3벌에서만 적중" if (d3 >= E.C["fire"] > d2) else ""
    print(f"    {t:6.1f} {x:6.3f} {y:6.3f} {z:6.3f}  {d2:7.3f} {d3:7.3f}{flag}")

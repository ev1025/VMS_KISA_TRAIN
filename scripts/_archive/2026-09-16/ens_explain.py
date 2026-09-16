# -*- coding: utf-8 -*-
"""앙상블이 실제로 무엇을 합치는지, 한 편을 표본 단위로 펼쳐 본다."""
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K      # noqa: E402
import fire_ens_try as E    # noqa: E402

TL = V / "dumps/score_tl"
FOG, SMALL = E.DEPLOY["fire_fog.pt"], E.DEPLOY["fire_small.pt"]
stem = sys.argv[1] if len(sys.argv) > 1 else "C00_195_0001"
lo, hi = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (110.0, 128.0)


def col(name):
    return {round(r[0], 2): r[1] for r in
            json.loads((TL / (name + ".json")).read_text(encoding="utf-8"))[stem]["rows"]}


a, b = col(FOG), col(SMALL)
th = K.ITEMS["fire"]["fire"]
print(f"{stem}   불 문턱 {th} · 창 {K.ITEMS['fire']['win']}표본 · {K.ITEMS['fire']['hits']}회")
print()
print("    시각   fire_fog@640  fire_small@960   둘 중 최고   적중")
na = nb = nm = 0
for t in sorted(a):
    if not (lo <= t <= hi):
        continue
    x, y = a.get(t, 0.0), b.get(t, 0.0)
    m = max(x, y)
    na += x >= th; nb += y >= th; nm += m >= th
    who = ""
    if m >= th:
        who = "  <- fog" if x >= th and y < th else ("  <- small" if y >= th and x < th else "  <- 둘 다")
    print(f"    {t:6.1f}   {x:10.3f}   {y:12.3f}   {m:10.3f}   {'O' if m >= th else '.'}{who}")
print()
print(f"이 구간 적중 수:  fog 만 {na}회 · small 만 {nb}회 · 합치면 {nm}회   (창에 {K.ITEMS['fire']['hits']}회 필요)")

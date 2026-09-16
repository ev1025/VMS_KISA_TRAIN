# -*- coding: utf-8 -*-
"""앙상블이 정말 '조기 경보를 양산' 하는가. 편마다 SA 가 정답보다 이른지 늦은지 센다.
   그리고 단일 가중치(fire_small)와 앙상블 중 어느 쪽이 더 단단한지 비교한다."""
import json
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K      # noqa: E402
import fire_ens_try as E    # noqa: E402

C = K.ITEMS["fire"]
FOG, SMALL = E.DEPLOY["fire_fog.pt"], E.DEPLOY["fire_small.pt"]


def report(label, names):
    d = E.merge(names)
    r, _, _ = E.evaluate(names)
    print(f"== {label}   점수 {r['점수']:.2f}  (정검 {r['정상검출']} 미검 {r['미검출']} 오검 {r['오검출']})")
    print(f"   {'클립':<16}{'GT':>6}{'SA':>8}{'차이':>8}{'창여유':>8}  {'판정':<6} 한표본만빼도깨짐")
    early = late = 0
    for stem in sorted(d):
        e = d[stem]; gt = e["gt"]; sa = E.judge(e["rows"])
        if sa is None:
            print(f"   {stem:<16}{gt:>6}{'-':>8}{'-':>8}{'-':>8}  미검"); continue
        diff = sa - gt
        lo, hi = round(sa - (gt - 2), 1), round(gt + 10 - sa, 1)
        ok = -2 <= diff <= 10
        if ok:
            early += diff < 0; late += diff >= 0
        # 표본 하나 제거 민감도
        killers = 0
        if ok:
            rows = e["rows"]
            for i, (t, f, s) in enumerate(rows):
                if f < C["fire"]:
                    continue
                cut = rows[:i] + rows[i + 1:]
                s2 = E.judge(cut)
                if s2 is None or not (gt - 2 <= s2 <= gt + 10):
                    killers += 1
        print(f"   {stem:<16}{gt:>6}{sa:>8.1f}{diff:>+8.1f}{min(lo,hi):>8.1f}  "
              f"{'정검' if ok else '창밖':<6} {killers if ok else '-'}")
    print(f"   -> 정검 중 이른 것 {early}편 · 늦은 것 {late}편")
    print()


report("앙상블 2벌 (지금 배포)", [FOG, SMALL])
report("fire_small 단독 @960", [SMALL])
report("fire_fog 단독 @640", [FOG])

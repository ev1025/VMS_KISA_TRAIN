# -*- coding: utf-8 -*-
"""침입 규칙을 전수로 훑는다. 검출이 좋아졌는데 점수가 안 오르면 규칙이 못 받아먹는 것이다.

쓰는 것은 덤프 하나뿐이라 추론을 다시 하지 않는다. 몇 초면 수백 조합을 본다.
판정기는 제출 도구의 IntrusionRule 을 그대로 쓴다(복사하지 않는다).

사용: python scripts/rule_sweep.py <덤프폴더> [<덤프폴더> ...]
"""
import itertools
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["intrusion"]
NOW = (CFG["conf"], CFG["corners"], CFG["hold"], CFG["settle"], CFG["gap"])


def load(dump):
    d = Path(dump)
    rows, poly, gt = {}, {}, {}
    for f in sorted(d.glob("*.jsonl")):
        s = f.stem
        rows[s] = [json.loads(l) for l in f.read_text().splitlines()]
        poly[s] = K.zone_of(str(KP.ZONE_MAPS), s, CFG["zone"], (1280, 720))
        g = next(KP.videos("침입").rglob(s + ".xml"), None)
        a = K.read_alarms(g) if g else []
        gt[s] = a[0]["start_s"] if a else None
    return rows, poly, gt


def score(rows, poly, gt, conf, corners, hold, settle, gap):
    pairs, miss = [], []
    for s in rows:
        j = K.IntrusionRule(poly[s], conf, corners, hold, settle, gap)
        for r in rows[s]:
            j.feed(r["t"], r["boxes"])
        sa = j.final()
        pairs.append(([{"start_s": gt[s], "desc": "I"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "I"}] if sa is not None else []))
        if gt[s] is not None and (sa is None or not (gt[s] - 2 <= sa <= gt[s] + 10)):
            miss.append(s.replace("C00_", ""))
    return K.score(pairs), miss


GRID = dict(
    # 미검 편의 구역 안 최고 신뢰도가 0.189~0.237 이라 0.25 부터 훑으면 그 편은 켜질 수가 없었다.
    # 아래로 넓힌다(2026-09-18). 낮추면 오검이 늘어 점수가 떨어지는지도 같이 본다.
    conf=[0.10, 0.15, 0.18, 0.20, 0.22, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55],
    corners=[0, 1, 2, 3, 4],
    hold=[1, 2, 3],
    settle=[12.0, 18.0, 24.0, 30.0],
    gap=[0, 1, 2, 3, 4, 6],
)

for dump in sys.argv[1:] or ["dumps/intrusion_tile_v3"]:
    rows, poly, gt = load(dump)
    if not rows:
        print(f"{dump}: 덤프 없음"); continue
    base, bmiss = score(rows, poly, gt, *NOW)
    print(f"== {dump}   {len(rows)}편")
    print(f"   지금 규칙 conf{NOW[0]} 꼭짓점{NOW[1]} 연속{NOW[2]} 대기{NOW[3]} 끊김{NOW[4]}"
          f"  ->  {base['점수']:.2f}  (정검 {base['정상검출']} 미검 {base['미검출']} 오검 {base['오검출']})")
    best = []
    n = 0
    for c, k, h, st, g in itertools.product(*GRID.values()):
        r, m = score(rows, poly, gt, c, k, h, st, g)
        best.append((r["점수"], (c, k, h, st, g), r, m)); n += 1
    best.sort(key=lambda x: -x[0])
    print(f"   {n}조합 훑음. 상위 6개")
    print(f"   {'점수':>7}  {'conf':>5}{'꼭짓점':>6}{'연속':>5}{'대기':>6}{'끊김':>5}  정검/미검/오검  못잡음")
    for sc, p, r, m in best[:6]:
        mark = "  <= 지금" if p == NOW else ""
        print(f"   {sc:>7.2f}  {p[0]:>5.2f}{p[1]:>6}{p[2]:>5}{p[3]:>6.0f}{p[4]:>5}"
              f"  {r['정상검출']:>2}/{r['미검출']}/{r['오검출']}  {m}{mark}")
    top = best[0][0]
    flat = sum(1 for sc, *_ in best if sc >= top - 0.01)
    print(f"   최고 {top:.2f} 를 내는 조합 {flat}개 " +
          ("(고원이라 믿을 만하다)" if flat >= 5 else "(단일 첨점이라 과적합 위험)"))
    print()

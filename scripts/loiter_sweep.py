# -*- coding: utf-8 -*-
"""배회 규칙을 전수로 훑는다. 검출이 좋아졌는데 점수가 안 오르면 규칙이 못 받아먹는 것이다.

쓰는 것은 덤프 하나뿐이라 추론을 다시 하지 않는다. 판정기는 제출 도구의 LoiterRule 을
그대로 쓴다(복사하지 않는다). scripts/rule_sweep.py 의 배회판이다.

배회는 침입과 달리 '같은 트랙 ID 로 dwell 초 체류' 를 요구한다. 그래서 트랙이 쪼개지면
검출이 충분해도 체류를 못 채운다. gap(끊김 허용)·dwell 이 그 지점을 만진다.

사용: python scripts/loiter_sweep.py [덤프폴더]
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

CFG = K.ITEMS["loitering"]
NOW = (CFG["conf"], CFG["corners"], CFG["dwell"], CFG["settle"], CFG["gap"])
DELAY = CFG["delay"]


def load(dump):
    d = Path(dump)
    rows, poly, gt = {}, {}, {}
    for f in sorted(d.glob("*.jsonl")):
        s = f.stem
        rows[s] = [json.loads(l) for l in f.read_text().splitlines()]
        poly[s] = K.zone_of(str(KP.ZONE_MAPS), s, CFG["zone"], (1280, 720))
        g = next(KP.videos("배회").rglob(s + ".xml"), None)
        a = K.read_alarms(g) if g else []
        gt[s] = a[0]["start_s"] if a else None
    return rows, poly, gt


def score(rows, poly, gt, conf, corners, dwell, settle, gap):
    pairs, miss = [], []
    for s in rows:
        j = K.LoiterRule(poly[s], conf, corners, dwell, settle, gap, CFG["stride"],
                         CFG["maxgap"], CFG["crowd"], CFG["still_in"])
        sa = None
        for r in rows[s]:
            v = j.feed(r["t"], r["boxes"])
            if v is not None and sa is None:
                sa = v + DELAY
        if sa is None:
            v = j.final() if hasattr(j, "final") else None
            sa = (v + DELAY) if v is not None else None
        pairs.append(([{"start_s": gt[s], "desc": "L"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "L"}] if sa is not None else []))
        if gt[s] is not None and (sa is None or not (gt[s] - 2 <= sa <= gt[s] + 10)):
            miss.append(s.replace("C00_", ""))
    return K.score(pairs), miss


GRID = dict(
    conf=[0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
    corners=[0, 1, 2],
    dwell=[3.0, 4.0, 5.0, 6.0, 8.0],
    settle=[3.0, 5.0, 8.0, 12.0],
    gap=[2, 4, 6, 10, 16],
)

for dump in sys.argv[1:] or ["dumps/loiter_botsort_v2"]:
    rows, poly, gt = load(dump)
    if not rows:
        print("%s: 덤프 없음" % dump); continue
    base, bmiss = score(rows, poly, gt, *NOW)
    print("== %s   %d편" % (dump, len(rows)))
    print("   지금 규칙 conf%.2f 꼭짓점%d 체류%.1f 대기%.1f 끊김%d  ->  %.2f  (정검 %d 미검 %d 오검 %d)"
          % (NOW[0], NOW[1], NOW[2], NOW[3], NOW[4], base["점수"],
             base["정상검출"], base["미검출"], base["오검출"]))
    print("   못잡음 %s" % bmiss)
    best, n = [], 0
    for c, k, dw, st, g in itertools.product(*GRID.values()):
        r, m = score(rows, poly, gt, c, k, dw, st, g)
        best.append((r["점수"], (c, k, dw, st, g), r, m)); n += 1
    best.sort(key=lambda x: -x[0])
    print("   %d조합 훑음. 상위 6개" % n)
    print("   %7s  %5s%6s%6s%6s%5s  정검/미검/오검  못잡음" % ("점수", "conf", "꼭짓점", "체류", "대기", "끊김"))
    for sc, p, r, m in best[:6]:
        mark = "  <= 지금" if p == NOW else ""
        print("   %7.2f  %5.2f%6d%6.1f%6.1f%5d  %2d/%d/%d  %s%s"
              % (sc, p[0], p[1], p[2], p[3], p[4], r["정상검출"], r["미검출"], r["오검출"], m, mark))
    top = best[0][0]
    flat = sum(1 for sc, *_ in best if sc >= top - 0.01)
    print("   최고 %.2f 를 내는 조합 %d개 %s"
          % (top, flat, "(고원이라 믿을 만하다)" if flat >= 5 else "(봉우리 하나라 과적합 의심)"))

# -*- coding: utf-8 -*-
"""배회 판정 규칙 대안(제미나이 제안 2026-09-18): 트랙 ID 를 무시하고 공간으로 누적한다.

왜
    지금 규칙은 '같은 트랙 ID 로 dwell 초 체류' 를 요구한다. 손라벨 모델은 검출은 되는데
    트랙이 3개로 쪼개져 7표본(3.5초어치)이 있어도 최장 체류가 2.0초로 끊겼다.
    BoT-SORT 를 건드리면 침입까지 흔들리므로, 판정 규칙에서 흡수한다.

규칙 agnostic
    표본마다 '구역 안에 conf>=c 인 사람이 있나' 만 본다(True/False). ID 는 안 본다.
    최근 win_s 초 창 안에서 True 가 need_s 초어치 이상이면 배회.
    경보 시각 = 그 창에서 첫 True 표본(체류 시작) + DELAY(배포와 같게 10초).
    구역이 gap_s 초 넘게 비었다가 다시 채워지면 새 체류로 본다(마지막 사람 정의).
    마지막 체류 시작 뒤 settle_s 동안 새 체류가 없으면 확정.

견고함 지표는 intr_rule3.py 와 같다(창위치·여유·간격·고원).

사용
    python scripts/loiter_rule3.py [덤프폴더 ...]
"""
import itertools
import json
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["loitering"]
STEP = CFG["stride"]
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


def sa_agnostic(rows, poly, conf_th, corners, win_s, need_s, gap_s, settle_s):
    q = deque()                       # (t, 사람있음)
    start = None                      # 지금 체류의 시작
    last_true = None
    latest = last_new = None
    for r in rows:
        t = r["t"]
        present = any(conf >= conf_th and K.entered((x1, y1, x2, y2), poly, corners)
                      for _pid, conf, x1, y1, x2, y2 in r["boxes"])
        if present:
            if last_true is None or t - last_true > gap_s:
                start = t                 # 오래 비었다 채워지면 새 체류
            last_true = t
        q.append((t, present))
        while q and t - q[0][0] > win_s:
            q.popleft()
        dwell = sum(STEP for _, p in q if p)
        if present and dwell >= need_s and start is not None:
            if latest is None or start > latest:
                latest, last_new = start, t
        if latest is not None and last_new is not None and t - last_new >= settle_s:
            return latest + DELAY
    return (latest + DELAY) if latest is not None else None


def sa_now(rows, poly):
    j = K.LoiterRule(poly, CFG["conf"], CFG["corners"], CFG["dwell"], CFG["settle"], CFG["gap"], STEP,
                     CFG["maxgap"], CFG["crowd"], CFG["still_in"])
    sa = None
    for r in rows:
        v = j.feed(r["t"], r["boxes"])
        if v is not None and sa is None:
            sa = v + DELAY
    if sa is None:
        v = j.final() if hasattr(j, "final") else None
        sa = (v + DELAY) if v is not None else None
    return sa


def zone_max_conf(rows, poly):
    m = 0.0
    for r in rows:
        for _pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if K.entered((x1, y1, x2, y2), poly, CFG["corners"]):
                m = max(m, conf)
    return m


def run(rows, poly, gt, zmax, fn):
    pairs, miss, offs, edge, tp_c, fn_c = [], [], [], [], [], []
    for s in rows:
        sa = fn(s)
        pairs.append(([{"start_s": gt[s], "desc": "L"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "L"}] if sa is not None else []))
        if gt[s] is None:
            continue
        ok = sa is not None and gt[s] - 2 <= sa <= gt[s] + 10
        if ok:
            offs.append(sa - gt[s]); edge.append(min(sa - (gt[s] - 2), (gt[s] + 10) - sa)); tp_c.append(zmax[s])
        else:
            miss.append(s.replace("C00_", "")); fn_c.append(zmax[s])
    r = K.score(pairs)
    gap = (min(tp_c) - max(fn_c)) if tp_c and fn_c else None
    return dict(score=r["점수"], tp=r["정상검출"], fn=r["미검출"], fp=r["오검출"], miss=miss,
                off=(sum(offs) / len(offs)) if offs else None, edge=min(edge) if edge else None, gap=gap)


def fmt(res):
    return ("%6.2f (%2d/%d/%d) 창위치 +%.1fs 여유 %.1fs 간격 %s"
            % (res["score"], res["tp"], res["fn"], res["fp"],
               res["off"] or 0, res["edge"] or 0, ("%.2f" % res["gap"]) if res["gap"] is not None else "-"))


GRID = dict(conf_th=[0.25, 0.30, 0.35, 0.40], corners=[0], win_s=[8.0, 10.0, 12.0],
            need_s=[4.0, 5.0, 6.0], gap_s=[3.0, 6.0, 10.0], settle_s=[5.0])

dumps = sys.argv[1:] or ["dumps/loiter_botsort_v2", "dumps/loiter_p1280hand_bs1280", "dumps/loiter_p1280ov2_bs1280"]
for dump in dumps:
    rows, poly, gt = load(dump)
    if not rows:
        print("\n===== %s : 덤프 없음" % dump); continue
    zmax = {s: zone_max_conf(rows[s], poly[s]) for s in rows}
    print("\n===== %s   %d편" % (dump, len(rows)))
    base = run(rows, poly, gt, zmax, lambda s: sa_now(rows[s], poly[s]))
    print("  지금 규칙(트랙ID)   %s" % fmt(base))
    print("                     못잡음 %s" % base["miss"])
    keys = list(GRID)
    best = []
    for vals in itertools.product(*GRID.values()):
        kw = dict(zip(keys, vals))
        res = run(rows, poly, gt, zmax, lambda s, kw=kw: sa_agnostic(rows[s], poly[s], **kw))
        best.append((res, kw))
    best.sort(key=lambda x: (-x[0]["score"], -(x[0]["edge"] or 0), -(x[0]["gap"] or -9)))
    top = best[0][0]["score"]
    flat = sum(1 for r, _ in best if r["score"] >= top - 0.01)
    print("  agnostic %4d조합  %s  고원 %d%s" % (len(best), fmt(best[0][0]), flat, "" if flat >= 5 else "  <- 봉우리"))
    print("                     못잡음 %s" % best[0][0]["miss"])
    print("                     설정   %s" % best[0][1])

# -*- coding: utf-8 -*-
"""침입 판정 규칙 대안(제미나이 제안 2026-09-18)을 덤프로 훑는다. 추론은 하지 않는다.

배경
    손라벨 모델은 정밀도 0.94 · 재현율 0.78 이다. 박스는 정확한데 깜빡이며 놓친다.
    지금 규칙(conf 0.45 이상이 연속 hold 표본)은 재현율이 높은 모델에 맞는 구조라,
    검출이 몇 표본 빠지면 판정이 끊긴다. 그래서 손라벨 모델은 검출이 좋아졌는데 점수가 낮다.

규칙 네 가지
    hyst      히스테리시스 + 밀도. 트리거는 엄격(hi), 한 번 트리거된 트랙은 낮은 문턱(lo)으로 유지.
              연속 대신 '최근 win 표본 중 유효 need 개' 로 센다. 깜빡여도 안 끊긴다.
    verified  트랙 생애 중 한 번이라도 conf>=vconf 를 찍었으면 '검증된 사람'. 그 트랙은 구역 안에서
              lo 만 넘어도 인정. 밝은 곳에서 얻은 확신을 어두운 구역 안까지 끌고 간다.
    inner     발끝(박스 하단 중심)이 구역 경계에서 margin 픽셀 이상 안쪽이어야 인정.
              가장자리를 스치는 사람을 거른다. dirin(진입 방향)의 발상을 연속값으로 바꾼 것이다.
    mindwell  구역 안 체류 dwell 초(끊김 gap 허용) 뒤에 경보. 지나가는 사람은 0.5초 밟고 사라진다.
              정답 창이 12초라 1~1.5초 기다려도 정검 안에 든다.

견고함 지표(점수 말고 같이 본다)
    창위치   정검 편들의 경보가 창 [GT-2, GT+10] 어디에 있나. 평균 오프셋(sa-GT)과 경계까지 최소 여유.
             경계에 붙은 정검은 실전에서 프레임 몇 장 밀리면 오검+미검이 된다.
    증거간격 정검 편 중 가장 약한 구역내 최고신뢰도 - 미검 편 중 가장 강한 구역내 최고신뢰도.
             넓을수록 처음 보는 영상에서 규칙이 안 깨진다.
    고원     최고점을 내는 조합 수. 1~2개면 봉우리(과적합).

사용
    python scripts/intr_rule3.py [덤프폴더 ...]
"""
import itertools
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["intrusion"]
STEP = CFG["stride"]
SETTLE = CFG["settle"]


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


def contour(poly):
    return np.array([[float(x), float(y)] for x, y in poly], dtype=np.float32).reshape(-1, 1, 2)


def foot_depth(box, cnt):
    """발끝(하단 중심)이 구역 안으로 몇 픽셀 들어왔나. 밖이면 음수."""
    x1, y1, x2, y2 = box
    return cv2.pointPolygonTest(cnt, (float((x1 + x2) / 2), float(y2)), True)


def finalize(latest, last_new, t):
    return latest is not None and last_new is not None and t - last_new >= SETTLE


# ---------------- 규칙들. 모두 (경보 시각 또는 None) 을 돌려준다 ----------------
def sa_hyst(rows, poly, corners, hi, lo, win, need, gap):
    armed, hist, entry = {}, defaultdict(deque), {}
    miss = {}
    latest = last_new = None
    for r in rows:
        t = r["t"]
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if not K.entered((x1, y1, x2, y2), poly, corners):
                continue
            if conf >= hi:
                armed[pid] = True                      # 확실할 때만 트리거
            if not armed.get(pid):
                continue
            if conf < lo:
                continue                               # 트리거 뒤엔 낮은 문턱으로 유지
            seen.add(pid)
            q = hist[pid]
            q.append(t)
            while q and t - q[0] > (win - 1) * STEP:
                q.popleft()
            if pid not in entry:
                entry[pid] = t
            miss[pid] = 0
            if len(q) >= need:
                if latest is None or entry[pid] > latest:
                    latest, last_new = entry[pid], t
        for pid in list(hist):
            if pid in seen:
                continue
            miss[pid] = miss.get(pid, 0) + 1
            if miss[pid] > gap:                        # 오래 끊기면 트랙을 다시 시작
                hist[pid].clear(); armed.pop(pid, None); entry.pop(pid, None)
        if finalize(latest, last_new, t):
            return latest
    return latest


def sa_verified(rows, poly, corners, vconf, hi, lo, hold, gap):
    verified, streak, miss, entry = set(), {}, {}, {}
    latest = last_new = None
    for r in rows:
        t = r["t"]
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if conf >= vconf:
                verified.add(pid)                      # 어디서든 한 번 확실했으면 검증된 사람
            if not K.entered((x1, y1, x2, y2), poly, corners):
                continue
            th = lo if pid in verified else hi
            if conf < th:
                continue
            seen.add(pid)
            if streak.get(pid, 0) == 0:
                entry[pid] = t
            streak[pid] = streak.get(pid, 0) + 1
            miss[pid] = 0
            if streak[pid] >= hold and (latest is None or entry[pid] > latest):
                latest, last_new = entry[pid], t
        for pid in list(streak):
            if pid in seen:
                continue
            miss[pid] = miss.get(pid, 0) + 1
            if miss[pid] > gap:
                streak[pid] = 0
        if finalize(latest, last_new, t):
            return latest
    return latest


def sa_inner(rows, poly, cnt, conf_th, margin, hold, gap):
    streak, miss, entry = {}, {}, {}
    latest = last_new = None
    for r in rows:
        t = r["t"]
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if conf < conf_th:
                continue
            if foot_depth((x1, y1, x2, y2), cnt) < margin:   # 경계에서 margin 픽셀 이상 안쪽이어야
                continue
            seen.add(pid)
            if streak.get(pid, 0) == 0:
                entry[pid] = t
            streak[pid] = streak.get(pid, 0) + 1
            miss[pid] = 0
            if streak[pid] >= hold and (latest is None or entry[pid] > latest):
                latest, last_new = entry[pid], t
        for pid in list(streak):
            if pid in seen:
                continue
            miss[pid] = miss.get(pid, 0) + 1
            if miss[pid] > gap:
                streak[pid] = 0
        if finalize(latest, last_new, t):
            return latest
    return latest


def sa_mindwell(rows, poly, corners, conf_th, dwell_s, gap):
    dwell, miss, entry = {}, {}, {}
    latest = last_new = None
    for r in rows:
        t = r["t"]
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if conf < conf_th or not K.entered((x1, y1, x2, y2), poly, corners):
                continue
            seen.add(pid)
            if dwell.get(pid, 0) == 0:
                entry[pid] = t
            dwell[pid] = dwell.get(pid, 0) + STEP
            miss[pid] = 0
            if dwell[pid] >= dwell_s and (latest is None or entry[pid] > latest):
                latest, last_new = entry[pid], t
        for pid in list(dwell):
            if pid in seen:
                continue
            miss[pid] = miss.get(pid, 0) + 1
            if miss[pid] > gap:
                dwell[pid] = 0
        if finalize(latest, last_new, t):
            return latest
    return latest


def sa_now(rows, poly):
    j = K.IntrusionRule(poly, CFG["conf"], CFG["corners"], CFG["hold"], CFG["settle"], CFG["gap"])
    for r in rows:
        j.feed(r["t"], r["boxes"])
    return j.final()


# ---------------- 채점 + 견고함 지표 ----------------
def zone_max_conf(rows, poly, corners=3):
    m = 0.0
    for r in rows:
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if K.entered((x1, y1, x2, y2), poly, corners):
                m = max(m, conf)
    return m


def run(rows, poly, gt, zmax, fn):
    pairs, miss, offs, edge, tp_conf, fn_conf = [], [], [], [], [], []
    for s in rows:
        sa = fn(s)
        pairs.append(([{"start_s": gt[s], "desc": "I"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "I"}] if sa is not None else []))
        if gt[s] is None:
            continue
        ok = sa is not None and gt[s] - 2 <= sa <= gt[s] + 10
        if ok:
            offs.append(sa - gt[s]); edge.append(min(sa - (gt[s] - 2), (gt[s] + 10) - sa)); tp_conf.append(zmax[s])
        else:
            miss.append(s.replace("C00_", "")); fn_conf.append(zmax[s])
    r = K.score(pairs)
    gap = (min(tp_conf) - max(fn_conf)) if tp_conf and fn_conf else None
    return dict(score=r["점수"], tp=r["정상검출"], fn=r["미검출"], fp=r["오검출"], miss=miss,
                off=(sum(offs) / len(offs)) if offs else None, edge=min(edge) if edge else None, gap=gap)


def fmt(res):
    return ("%6.2f (%2d/%d/%d) 창위치 +%.1fs 여유 %.1fs 간격 %s"
            % (res["score"], res["tp"], res["fn"], res["fp"],
               res["off"] if res["off"] is not None else 0, res["edge"] if res["edge"] is not None else 0,
               ("%.2f" % res["gap"]) if res["gap"] is not None else "-"))


GRIDS = {
    "hyst": dict(corners=[0, 3], hi=[0.40, 0.45, 0.50], lo=[0.15, 0.20, 0.25], win=[6, 10], need=[2, 3, 4], gap=[2, 4]),
    "verified": dict(corners=[0, 3], vconf=[0.55, 0.65, 0.75], hi=[0.40, 0.45], lo=[0.15, 0.20, 0.25], hold=[1, 2, 3], gap=[2]),
    "inner": dict(conf_th=[0.30, 0.35, 0.40, 0.45], margin=[0, 10, 20, 40, 60], hold=[1, 2, 3], gap=[2]),
    "mindwell": dict(corners=[0, 3], conf_th=[0.30, 0.35, 0.40, 0.45], dwell_s=[1.0, 1.5, 2.0], gap=[2, 4]),
}

dumps = sys.argv[1:] or ["dumps/intrusion_tile_v3", "dumps/intrusion_p1280hand_1280", "dumps/intrusion_p1280ov2_1280"]
for dump in dumps:
    rows, poly, gt = load(dump)
    if not rows:
        print("\n===== %s : 덤프 없음" % dump); continue
    cnt = {s: contour(poly[s]) for s in rows}
    zmax = {s: zone_max_conf(rows[s], poly[s]) for s in rows}
    print("\n===== %s   %d편" % (dump, len(rows)))
    base = run(rows, poly, gt, zmax, lambda s: sa_now(rows[s], poly[s]))
    print("  지금 규칙          %s" % fmt(base))
    print("                     못잡음 %s" % base["miss"])
    for name, grid in GRIDS.items():
        keys = list(grid)
        best = []
        for vals in itertools.product(*grid.values()):
            kw = dict(zip(keys, vals))
            if name == "hyst":
                fn = lambda s, kw=kw: sa_hyst(rows[s], poly[s], **kw)
            elif name == "verified":
                fn = lambda s, kw=kw: sa_verified(rows[s], poly[s], **kw)
            elif name == "inner":
                fn = lambda s, kw=kw: sa_inner(rows[s], poly[s], cnt[s], **kw)
            else:
                fn = lambda s, kw=kw: sa_mindwell(rows[s], poly[s], **kw)
            res = run(rows, poly, gt, zmax, fn)
            best.append((res, kw))
        best.sort(key=lambda x: (-x[0]["score"], -(x[0]["edge"] or 0), -(x[0]["gap"] or -9)))
        top = best[0][0]["score"]
        flat = sum(1 for r, _ in best if r["score"] >= top - 0.01)
        print("  %-9s %4d조합  %s  고원 %d%s" % (name, len(best), fmt(best[0][0]), flat,
                                              "" if flat >= 5 else "  <- 봉우리"))
        print("                     못잡음 %s" % best[0][0]["miss"])
        print("                     설정   %s" % best[0][1])

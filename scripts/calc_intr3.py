# -*- coding: utf-8 -*-
"""침입 3단계 규칙 후보 3가지(딥리서치 10-03, 히스토리 h1003j)를 기존 덤프 위에서 비교한다(서버 B, GPU 없음).
바탕 = 지금 기준선 규칙 B(초당 6장 · conf 0.35 · 꼭짓점 4 · hold 0.5초 · 끊김 2초 · 추적 5초). 바탕 위에 한 가지씩, 그리고 다 합쳐서:
  H 경계 이력(hysteresis): 발끝이 경계 안쪽으로 hin px 이상 들어와야 '안', 바깥으로 hout px 이상 나가야 '밖', 그 사이는 이전 상태 유지
                           (꼭짓점 조건은 그대로). 경계 왕복 · 박스 흔들림(사전시험 실패)을 겨냥
  M 메타 트랙 병합(merge): 사라진 번호를 ms 초 · mr px(사라진 자리 기준, 시간에 따라 넓어짐) 안에 새로 나타난 번호에 이어 준다(외형 특징 없이).
                           이어진 번호는 옛 번호의 진입 시각 · 연속 수를 물려받아 '새 사람' 으로 안 잡힘 → 늦은 경보를 겨냥
  O OC-SORT 간이판(관측 중심): 표본 사이 움직임 벡터로 다음 위치를 예측해 IoU 를 재고(모멘텀), 놓친 동안은 마지막 관측을 그대로 두고
                           다시 잡히면 그 사이를 직선으로 메운다(관측 중심 복구). 칼만 필터 없음(6fps 에서 등속 가정이 틀리는 문제를 피함)
고르기 = 안 본 연구개발 편(lists/unseen_intr.txt) 정검 합 → 채점편은 측정만(이 스크립트는 두 셋 다 돌리고 표로 보여 줌)
  python calc_intr3.py --models p1280_grid_b170_bg10_20260929_last [--set rd --clips lists/unseen_intr.txt] [--jobs 40]"""
import argparse
import itertools
import json
import math
from multiprocessing import Pool

import common as C
import calc_intr as CI

K = C.K
DESC = K.ITEMS["intrusion"]["desc"]
RATE = 6
BASE = dict(conf=0.35, corners=4, hold_s=0.5, gap_s=2.0, trk_s=5.0)          # 지금 기준선 규칙 B(10-01 3단계 결과)
HYS = [(0, 0), (5, 10), (10, 15), (15, 25)]                                  # (안으로 hin, 밖으로 hout) px. (0, 0) = 없음
MERGE = [(0, 0), (5, 80), (10, 120), (20, 160)]                              # (ms 초, mr px). (0, 0) = 없음
TRK = ["iou", "oc"]                                                          # 추적기


def dist_to_poly(px, py, poly):
    """점에서 다각형 경계까지 거리(px). 안이면 양수 · 밖이면 음수"""
    best = 1e18
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        dx, dy = x2 - x1, y2 - y1
        L = dx * dx + dy * dy
        u = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
        best = min(best, math.hypot(px - (x1 + u * dx), py - (y1 + u * dy)))
    return best if K.in_poly(px, py, poly) else -best


class OCTracker:
    """OC-SORT 간이판. 상태 = 마지막 관측 박스 · 속도(표본당 px). 예측 박스 = 마지막 박스 + 속도 × 놓친 표본 수.
    연관 = 예측 박스 IoU(iou_thr) → 없으면 중심 거리(판정기 Tracker 와 같은 상한). 다시 잡히면 속도를 관측 차이로 갱신(관측 중심)"""

    def __init__(self, iou_thr=0.25, max_gap=30, momentum=0.5):
        self.iou_thr, self.max_gap, self.mom = iou_thr, max_gap, momentum
        self.tracks, self.next_id = [], 1

    def _pred(self, t):
        n = t["miss"]
        return tuple(b + v * n for b, v in zip(t["box"], t["vel"]))

    def update(self, dets):
        for t in self.tracks:
            t["miss"] += 1
        out, used = [], set()
        for conf, x1, y1, x2, y2 in sorted(dets, key=lambda d: -d[0]):
            box = (x1, y1, x2, y2)
            best, bi = self.iou_thr, None
            for i, t in enumerate(self.tracks):
                if i in used:
                    continue
                v = K.iou(box, self._pred(t))
                if v > best:
                    best, bi = v, i
            if bi is None:
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                dbest, di = 1e18, None
                for i, t in enumerate(self.tracks):
                    if i in used:
                        continue
                    px1, py1, px2, py2 = self._pred(t)
                    d = math.hypot(cx - (px1 + px2) / 2, cy - (py1 + py2) / 2)
                    lim = max(60.0, 0.8 * max(x2 - x1, y2 - y1)) * (1 + t["miss"])
                    if d < dbest and d <= lim:
                        dbest, di = d, i
                bi = di
            if bi is None:
                self.tracks.append({"id": self.next_id, "box": box, "vel": (0.0, 0.0, 0.0, 0.0), "miss": 0})
                used.add(len(self.tracks) - 1)
                out.append((self.next_id, round(conf, 3), *box))
                self.next_id += 1
            else:
                t = self.tracks[bi]; n = max(1, t["miss"])
                newv = tuple((b - o) / n for b, o in zip(box, t["box"]))           # 놓친 동안의 평균 속도(관측 중심 복구)
                t["vel"] = tuple(self.mom * nv + (1 - self.mom) * ov for nv, ov in zip(newv, t["vel"]))
                t["box"] = box; t["miss"] = 0; used.add(bi)
                out.append((t["id"], round(conf, 3), *box))
        self.tracks = [t for t in self.tracks if t["miss"] <= self.max_gap]
        return out


def merge_ids(tracked, ms, mr, rate):
    """메타 트랙 병합: 번호가 사라진 뒤 ms 초 안에, 사라진 자리에서 mr × (1 + 지난 초/ms) px 안에 새 번호가 처음 나타나면 옛 번호로 바꿔 준다"""
    if ms <= 0:
        return tracked
    alias, lost, seen_first = {}, {}, {}
    out = []
    for t, boxes in tracked:
        ids_now = {pid for pid, *_ in boxes}
        for pid in list(lost):
            if t - lost[pid][0] > ms:
                del lost[pid]
        new_boxes = []
        for pid, conf, x1, y1, x2, y2 in boxes:
            pid = alias.get(pid, pid)
            if pid not in seen_first:
                seen_first[pid] = t
                foot = ((x1 + x2) / 2, y2)
                cand = None; dbest = 1e18
                for lid, (lt, lfoot) in lost.items():
                    d = math.hypot(foot[0] - lfoot[0], foot[1] - lfoot[1])
                    lim = mr * (1 + (t - lt) / ms)
                    if d <= lim and d < dbest:
                        dbest, cand = d, lid
                if cand is not None:
                    alias[pid] = cand; del lost[cand]; pid = cand
            new_boxes.append((pid, conf, x1, y1, x2, y2))
        now = {pid for pid, *_ in new_boxes}
        for pid, conf, x1, y1, x2, y2 in out[-1][1] if out else []:
            if pid not in now and pid not in lost:
                lost[pid] = (out[-1][0], ((x1 + x2) / 2, y2))
        out.append((t, new_boxes))
    return out


class Rule3(CI.Rule):
    """기준선 규칙 B + 경계 이력(hin · hout). 발끝 상태를 번호마다 기억: 안쪽 hin 이상이면 안, 바깥 hout 이상이면 밖, 사이는 이전 상태"""

    def __init__(self, poly, conf, corners, hold, settle, gap, hin, hout):
        super().__init__(poly, conf, corners, hold, settle, gap, 0)
        self.hin, self.hout, self.state = hin, hout, {}

    def feed(self, t, boxes):
        if self.settled is not None:
            return self.settled
        seen = set()
        for pid, conf, x1, y1, x2, y2 in boxes:
            if conf < self.conf:
                continue
            if self.hin or self.hout:
                d = dist_to_poly((x1 + x2) / 2, y2, self.poly)
                prev = self.state.get(pid, False)
                inside_foot = True if d >= self.hin else (False if d <= -self.hout else prev)
                self.state[pid] = inside_foot
                corners_ok = sum(K.in_poly(cx, cy, self.poly) for cx, cy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2))) >= self.corners
                inside = inside_foot and corners_ok
            else:
                inside = K.entered((x1, y1, x2, y2), self.poly, self.corners)
            if not inside:
                continue
            seen.add(pid)
            self.miss[pid] = 0
            self.streak[pid] = self.streak.get(pid, 0) + 1
            if self.streak[pid] >= self.hold and pid not in self.entry:
                self.entry[pid] = t
                self.latest = t if self.latest is None else max(self.latest, t)
                self.last_new = t
        for pid in list(self.streak):
            if pid not in seen:
                self.miss[pid] = self.miss.get(pid, 0) + 1
                if self.miss[pid] > self.gap:
                    self.streak[pid] = 0
        if self.latest is not None and t - self.last_new >= self.settle - K.T_EPS:
            self.settled = self.latest
        return self.settled


def key(trk, hys, mrg):
    return "%s|h%d_%d|m%d_%d" % (trk, hys[0], hys[1], mrg[0], mrg[1])


def one(job):
    model, set_, stem = job
    d = json.loads((C.OUT / "intr" / model / set_ / (stem + ".json")).read_text(encoding="utf-8"))
    fps = d["fps"]
    xml = C.VIDEOS[("intrusion", set_)] / (stem + ".xml")
    gts = [g for g in (K.read_alarms(xml) if xml.exists() else []) if g["desc"] == DESC]
    poly = K.zone_of(C.MAPS[set_], stem, "Intrusion", (1280, 720))
    step = max(1, int(round(fps / RATE)))
    rows = [(i / fps, dets) for i, dets in d["rows"] if i % step == 0]
    out = {}
    for trk in TRK:
        gapn = max(1, int(round(BASE["trk_s"] * RATE)))
        tr = K.Tracker(iou_thr=0.25, max_gap=gapn) if trk == "iou" else OCTracker(iou_thr=0.25, max_gap=gapn)
        tracked0 = [(t, tr.update([tuple(x) for x in dets])) for t, dets in rows]
        for mrg in MERGE:
            tracked = merge_ids(tracked0, mrg[0], mrg[1], RATE)
            for hys in HYS:
                rule = Rule3(poly, BASE["conf"], BASE["corners"], max(1, int(round(BASE["hold_s"] * RATE))), 24.0, int(round(BASE["gap_s"] * RATE)), hys[0], hys[1])
                onset = None
                for t, boxes in tracked:
                    onset = rule.feed(t, boxes)
                    if onset is not None:
                        break
                if onset is None:
                    onset = rule.final()
                sas = [{"start_s": onset, "desc": DESC}] if onset is not None else []
                s = K.score([(gts, sas)])
                out[key(trk, hys, mrg)] = [s["정상검출"], s["미검출"], s["오검출"]]
    return model, stem, out


def f1(s):
    tp, fn, fp = s
    return 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--jobs", type=int, default=40)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
        assert abs(dist_to_poly(50, 50, poly) - 50) < 1e-9 and abs(dist_to_poly(120, 50, poly) + 20) < 1e-9 and abs(dist_to_poly(50, 3, poly) - 3) < 1e-9
        tr = OCTracker(); a1 = tr.update([(0.9, 0, 0, 10, 10)]); a2 = tr.update([(0.9, 20, 0, 30, 10)]); tr.update([]); tr.update([]); a3 = tr.update([(0.9, 80, 0, 90, 10)])
        assert a1[0][0] == a2[0][0] == a3[0][0], (a1, a2, a3)          # 표본당 20px 로 가다 2표본 놓친 뒤 예측 자리(80) 에서 다시 잡힘 = 같은 번호
        tk = [(0.0, [(1, 0.9, 0, 0, 10, 20)]), (1.0, []), (2.0, [(2, 0.9, 5, 0, 15, 20)])]
        m = merge_ids(tk, 5, 80, 6); assert m[2][1][0][0] == 1, m                         # 1초 뒤 5px 옆에 새 번호 → 옛 번호로
        m = merge_ids(tk, 0, 0, 6); assert m[2][1][0][0] == 2
        print("자체 점검 통과"); return
    res = {}
    for set_, clips in (("rd", "lists/unseen_intr.txt"), ("score", None)):
        stems = [v.stem for v in C.videos("intrusion", set_, clips)]
        jobs = [(m, set_, s) for m in a.models for s in stems if (C.OUT / "intr" / m / set_ / (s + ".json")).exists()]
        with Pool(a.jobs) as p:
            for model, stem, per in p.imap_unordered(one, jobs, chunksize=1):
                R = res.setdefault(model, {}).setdefault(set_, {"n": 0, "rules": {}})
                R["n"] += 1
                for k, c in per.items():
                    s = R["rules"].setdefault(k, [0, 0, 0])
                    for i in range(3):
                        s[i] += c[i]
    C.save(C.E / "results" / "intr3_rules.json", res)
    for m, S in res.items():
        rd, sc = S.get("rd", {}), S.get("score", {})
        print(f"\n== {m}: 안 본 연구개발 {rd.get('n')}편 · 채점 {sc.get('n')}편 · 초당 6장 · 기준선 B 위에서")
        print(f"{'규칙':22s} {'안본 F1':>8s} {'정/미/오':>12s} | {'채점 F1':>8s} {'정/미/오':>12s}")
        rows = sorted(rd["rules"].items(), key=lambda kv: (-f1(kv[1]), kv[0]))
        for k, v in rows:
            w = sc["rules"].get(k, [0, 0, 0])
            mark = "  <- 지금" if k == "iou|h0_0|m0_0" else ""
            print(f"{k:22s} {f1(v):8.1f} {str(v):>12s} | {f1(w):8.1f} {str(w):>12s}{mark}")


if __name__ == "__main__":
    main()

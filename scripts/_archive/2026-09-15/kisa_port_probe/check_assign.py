# -*- coding: utf-8 -*-
"""손라벨 참조 번호 배정(현재 JS 규칙 재현)으로 최근 편집 클립들의 궤적을 뽑아 '섞임'(큰 점프·교차) 지점을 찍는다."""
import json, io, sys, math, collections
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
clips = sys.argv[1:]
rows = json.load(io.open(f"{V}/data/학습데이터/손라벨/person_labels.json", encoding="utf-8"))

def iou(a, b):
    x1 = max(a[1], b[1]); y1 = max(a[2], b[2]); x2 = min(a[1] + a[3], b[1] + b[3]); y2 = min(a[2] + a[4], b[2] + b[4])
    i = max(0, x2 - x1) * max(0, y2 - y1); return i / (a[3] * a[4] + b[3] * b[4] - i + 1e-9)

for clip in clips:
    byf = collections.defaultdict(list)
    for r in rows:
        if r["clip"] == clip and r["cls"] >= 0:
            byf[round(float(r["t"]) * 2) / 2].append([r["cls"], r["x"], r["y"], r["w"], r["h"]])
    frames = sorted(byf)
    last = {}; nxt = 0; seeds = []
    for t in frames:
        taken = []; cand = []
        for i, b in enumerate(byf[t]):
            if any(iou(q, b) > 0.7 for q in taken): continue
            taken.append(b); cand.append({"b": b, "cx": b[1] + b[3] / 2, "cy": b[2] + b[4] / 2, "obj": None})
        pairs = []
        for ci, c in enumerate(cand):
            for k, q in last.items():
                dt = max(0, t - q["t"]); dtp = min(dt, 2)
                px = q["cx"] + q.get("vx", 0) * dtp; py = q["cy"] + q.get("vy", 0) * dtp
                tol = min(0.3, 0.08 + 0.03 * dt); d = math.hypot(px - c["cx"], py - c["cy"])
                if d < tol: pairs.append((d / tol, ci, k, d, tol))
        pairs.sort()
        used = set()
        for sc, ci, k, d, tol in pairs:
            if cand[ci]["obj"] is not None or k in used: continue
            cand[ci]["obj"] = k; used.add(k)
        for c in cand:
            if c["obj"] is None: nxt += 1; c["obj"] = nxt
            q0 = last.get(c["obj"]); dt0 = (t - q0["t"]) if q0 else 0
            last[c["obj"]] = {"cx": c["cx"], "cy": c["cy"], "t": t, "vx": (c["cx"] - q0["cx"]) / dt0 if q0 and dt0 > 0 else 0, "vy": (c["cy"] - q0["cy"]) / dt0 if q0 and dt0 > 0 else 0}
            seeds.append((t, c["obj"], c["cx"], c["cy"], c["b"][3], c["b"][4]))
    objs = sorted({s[1] for s in seeds})
    print(f"\n==== {clip}: 손라벨 {len(frames)}프레임 · 객체 {len(objs)}개 {dict(collections.Counter(s[1] for s in seeds))}")
    # 프레임별 박스 수 분포와 결측
    print("  프레임당 박스 수:", dict(collections.Counter(len(byf[t]) for t in frames)))
    for o in objs:
        seq = [s for s in seeds if s[1] == o]
        jumps = []
        for a, b in zip(seq, seq[1:]):
            dt = b[0] - a[0]; d = math.hypot(b[2] - a[2], b[3] - a[3])
            if d > 0.06 + 0.06 * dt: jumps.append((a[0], b[0], round(a[2], 3), round(b[2], 3)))
        print(f"  객체 {o}: {len(seq)}개 t {seq[0][0]}~{seq[-1][0]}  점프 {len(jumps)} {jumps[:4]}")
    # 두 객체가 같은 프레임에서 아주 가까운(교차) 순간
    near = []
    for t in frames:
        ss = [s for s in seeds if s[0] == t]
        for i in range(len(ss)):
            for j in range(i + 1, len(ss)):
                d = math.hypot(ss[i][2] - ss[j][2], ss[i][3] - ss[j][3])
                if d < 0.06: near.append((t, ss[i][1], ss[j][1], round(d, 3)))
    print("  두 객체가 겹치듯 가까운 프레임(교차 의심):", near[:8])
    # 결측 구간(연속 프레임 사이 1.5초 넘는 빈틈)
    gaps = [(a, b) for a, b in zip(frames, frames[1:]) if b - a > 1.5]
    print("  라벨 빈틈(1.5초 초과):", gaps[:8])

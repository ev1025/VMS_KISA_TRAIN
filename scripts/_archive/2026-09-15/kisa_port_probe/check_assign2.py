# -*- coding: utf-8 -*-
"""새 배정 규칙 검증: 간격 2초 이하 = 속도 예측 + 가까운 순 확정 / 간격 2초 초과 = 박스 수와 최근 객체 수가 같으면 좌→우 순서로 짝지음(무리 이동), 아니면 가까운 순."""
import json, io, sys, math, collections
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
rows = json.load(io.open(f"{V}/data/학습데이터/손라벨/person_labels.json", encoding="utf-8"))
def iou(a, b):
    x1 = max(a[1], b[1]); y1 = max(a[2], b[2]); x2 = min(a[1] + a[3], b[1] + b[3]); y2 = min(a[2] + a[4], b[2] + b[4])
    i = max(0, x2 - x1) * max(0, y2 - y1); return i / (a[3] * a[4] + b[3] * b[4] - i + 1e-9)

def assign(byf, order_rule=True):
    frames = sorted(byf); last = {}; nxt = 0; seeds = []
    for t in frames:
        taken = []; cand = []
        for b in byf[t]:
            if any(iou(q, b) > 0.7 for q in taken): continue
            taken.append(b); cand.append({"b": b, "cx": b[1] + b[3] / 2, "cy": b[2] + b[4] / 2, "obj": None})
        recent = {k: q for k, q in last.items() if t - q["t"] <= 30}
        gap = min([t - q["t"] for q in recent.values()], default=0)
        done = False
        if order_rule and recent and gap > 2 and len(cand) == len(recent):
            cs = sorted(cand, key=lambda c: c["cx"]); ks = sorted(recent, key=lambda k: recent[k]["cx"])
            ok = all(math.hypot(recent[k]["cx"] - c["cx"], recent[k]["cy"] - c["cy"]) < min(0.3, 0.08 + 0.03 * (t - recent[k]["t"])) for c, k in zip(cs, ks))
            if ok:
                for c, k in zip(cs, ks): c["obj"] = k
                done = True
        if not done:
            pairs = []
            for ci, c in enumerate(cand):
                for k, q in last.items():
                    dt = max(0, t - q["t"]); dtp = min(dt, 2)
                    px = q["cx"] + q.get("vx", 0) * dtp; py = q["cy"] + q.get("vy", 0) * dtp
                    tol = min(0.3, 0.08 + 0.03 * dt); d = math.hypot(px - c["cx"], py - c["cy"])
                    if d < tol: pairs.append((d / tol, ci, k))
            pairs.sort(); used = set()
            for sc, ci, k in pairs:
                if cand[ci]["obj"] is not None or k in used: continue
                cand[ci]["obj"] = k; used.add(k)
        for c in cand:
            if c["obj"] is None: nxt += 1; c["obj"] = nxt
            q0 = last.get(c["obj"]); dt0 = (t - q0["t"]) if q0 else 0
            last[c["obj"]] = {"cx": c["cx"], "cy": c["cy"], "t": t, "vx": (c["cx"] - q0["cx"]) / dt0 if q0 and dt0 > 0 else 0, "vy": (c["cy"] - q0["cy"]) / dt0 if q0 and dt0 > 0 else 0}
            seeds.append((t, c["obj"], round(c["cx"], 3)))
    return seeds

for clip in sys.argv[1:]:
    byf = collections.defaultdict(list)
    for r in rows:
        if r["clip"] == clip and r["cls"] >= 0: byf[round(float(r["t"]) * 2) / 2].append([r["cls"], r["x"], r["y"], r["w"], r["h"]])
    for name, rule in (("현재(가까운 순)", False), ("새 규칙(순서 유지)", True)):
        seeds = assign(byf, rule); objs = sorted({s[1] for s in seeds})
        print(f"\n== {clip} [{name}] 객체 {len(objs)}개 {dict(collections.Counter(s[1] for s in seeds))}")
        frames = sorted(byf)
        gaps = [(a, b) for a, b in zip(frames, frames[1:]) if b - a > 2]
        for a, b in gaps[:6]:
            sa = sorted([(s[1], s[2]) for s in seeds if s[0] == a]); sb = sorted([(s[1], s[2]) for s in seeds if s[0] == b])
            print(f"   {a} {sa}  →  {b} {sb}")

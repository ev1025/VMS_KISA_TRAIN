# -*- coding: utf-8 -*-
"""C049100_005 전파 드리프트 진단(서버·저장소 건드리지 않음: serve_kisa 의 함수를 직접 호출).
A) 왼쪽 사람(객체1) 참조샷 전부(186.5~200)  B) 첫 참조샷 1개  C) 세 객체 참조샷(손라벨참조 배정 규칙) 함께"""
import json, io, sys, math, collections, time
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
sys.path.insert(0, V + "/dash_v2")
import serve_kisa as S
CLIP = "kisa_연구개발_사람영상/1. 배회(325개)/C049100_005"
rows = [r for r in json.load(io.open(f"{V}/data/학습데이터/손라벨/person_labels.json", encoding="utf-8")) if r["clip"] == "C049100_005" and r["cls"] >= 0]
byf = collections.defaultdict(list)
for r in rows: byf[round(float(r["t"]) * 2) / 2].append([r["cls"], r["x"], r["y"], r["w"], r["h"]])
T0, T1 = 186.5, 200.0
frames = [t for t in sorted(byf) if T0 <= t <= T1]

def iou(a, b):
    x1 = max(a[1], b[1]); y1 = max(a[2], b[2]); x2 = min(a[1] + a[3], b[1] + b[3]); y2 = min(a[2] + a[4], b[2] + b[4])
    i = max(0, x2 - x1) * max(0, y2 - y1); return i / (a[3] * a[4] + b[3] * b[4] - i + 1e-9)
# 손라벨참조 배정 규칙(현재 JS)
last = {}; nxt = 0; assigned = []
for t in frames:
    used = set(); taken = []
    for b in byf[t]:
        if any(iou(q, b) > 0.7 for q in taken): continue
        taken.append(b); cx, cy = b[1] + b[3] / 2, b[2] + b[4] / 2
        best, bs = None, 1e9
        for o, q in last.items():
            if o in used: continue
            tol = min(0.5, 0.15 + 0.05 * max(0, t - q["t"])); d = math.hypot(q["cx"] - cx, q["cy"] - cy)
            if d < tol and d / tol < bs: bs, best = d / tol, o
        if best is None: nxt += 1; best = nxt
        used.add(best); last[best] = {"cx": cx, "cy": cy, "t": t}
        assigned.append({"t": t, "obj": best, "box": b[1:5]})
seedsA = [s for s in assigned if s["obj"] == 1]
print("배정 결과 객체별 수", collections.Counter(s["obj"] for s in assigned))
print("객체1 참조 궤적", [(s["t"], round(s["box"][0] + s["box"][2] / 2, 3)) for s in seedsA])

def show(tag, seeds, out):
    ref = {(s["t"], s["obj"]): s["box"][0] + s["box"][2] / 2 for s in seeds}
    print(f"\n[{tag}] 결과 프레임 {len(out)}")
    bad = 0
    for k in sorted(out, key=float):
        t = float(k); cx = {o: round(b[0] + b[2] / 2, 3) for o, b in out[k].items()}
        marks = []
        for o, c in cx.items():
            r = ref.get((t, int(o)))
            if r is not None and abs(c - r) > 0.05: marks.append(f"객체{o} 참조 {r:.3f} 어긋남"); bad += 1
        print(f"  t={t:6.1f} {cx} {' | '.join(marks)}")
    print(f"  참조 프레임에서 어긋난 수: {bad}")

for tag, sd in [("A 객체1 참조샷 전부", seedsA), ("B 객체1 첫 참조샷만", seedsA[:1]), ("C 세 객체 함께", assigned)]:
    tic = time.time()
    out, sec, err = S.sam2_propagate_objs(CLIP, sd, back=0.0, fwd=max(0.0, T1 - max(s["t"] for s in sd)), step=0.5)
    print(f"\n==== {tag}: {len(sd)}개 참조샷, {sec}s, err={err}")
    show(tag, sd, out)

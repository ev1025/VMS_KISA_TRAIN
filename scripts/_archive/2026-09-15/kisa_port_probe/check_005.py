# -*- coding: utf-8 -*-
"""C049100_005: 손라벨 → 손라벨참조 번호 배정 재현(JS 와 같은 규칙) → 번호 뒤바뀜 점검, SAM 저장소 결과와 비교."""
import json, io, collections, math
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
CLIP = "C049100_005"
rows = [r for r in json.load(io.open(f"{V}/data/학습데이터/손라벨/person_labels.json", encoding="utf-8")) if r["clip"] == CLIP and r["cls"] >= 0]
byf = collections.defaultdict(list)
for r in rows: byf[round(float(r["t"]) * 2) / 2].append([r["cls"], r["x"], r["y"], r["w"], r["h"]])
frames = sorted(byf)
print(f"손라벨 프레임 {len(frames)}개, 박스 {len(rows)}개, 범위 {frames[0]}~{frames[-1]}")
cnt = collections.Counter(len(byf[t]) for t in frames); print("프레임당 박스 수 분포", dict(cnt))

def iou(a, b):
    x1 = max(a[1], b[1]); y1 = max(a[2], b[2]); x2 = min(a[1] + a[3], b[1] + b[3]); y2 = min(a[2] + a[4], b[2] + b[4])
    i = max(0, x2 - x1) * max(0, y2 - y1); return i / (a[3] * a[4] + b[3] * b[4] - i + 1e-9)

# JS 규칙 재현: 각 객체의 마지막 위치와 비교, tol = min(0.5, 0.15+0.05*gap), 점수 = d/tol 최소
last = {}; nxt = 0; seeds = []
for t in frames:
    used = set(); taken = []
    for b in byf[t]:
        if any(iou(q, b) > 0.7 for q in taken): continue
        taken.append(b)
        cx, cy = b[1] + b[3] / 2, b[2] + b[4] / 2
        best, bs = None, 1e9
        for o, q in last.items():
            if o in used: continue
            tol = min(0.5, 0.15 + 0.05 * max(0, t - q["t"])); d = math.hypot(q["cx"] - cx, q["cy"] - cy)
            if d < tol and d / tol < bs: bs, best = d / tol, o
        if best is None: nxt += 1; best = nxt
        used.add(best); last[best] = {"cx": cx, "cy": cy, "t": t}
        seeds.append((t, best, cx, cy, b[3], b[4]))
objs = sorted({s[1] for s in seeds}); print("배정된 객체", objs, {o: sum(1 for s in seeds if s[1] == o) for o in objs})
# 궤적 출력(객체별 cx 시계열, 큰 점프 표시)
for o in objs:
    seq = [s for s in seeds if s[1] == o]
    print(f"\n객체 {o}: {len(seq)}개  t {seq[0][0]}~{seq[-1][0]}")
    line = []; prev = None
    for s in seq:
        flag = ""
        if prev is not None and math.hypot(s[2] - prev[2], s[3] - prev[3]) > 0.08: flag = "  <-- 점프"
        line.append(f"  t={s[0]:6.1f} cx={s[2]:.3f} cy={s[3]:.3f} w={s[4]:.3f}{flag}")
        prev = s
    print("\n".join(line[:8] + (["  ..."] if len(line) > 16 else []) + line[-8:] if len(line) > 16 else line))
# 같은 프레임에 같은 객체가 둘? 프레임별 객체 집합
dup = [(t, [s[1] for s in seeds if s[0] == t]) for t in frames if len([s for s in seeds if s[0] == t]) != len({s[1] for s in seeds if s[0] == t})]
print("\n같은 프레임 중복 객체:", dup[:5])
# 프레임별 어떤 객체가 빠졌나(3객체 기준)
miss = collections.Counter()
for t in frames:
    have = {s[1] for s in seeds if s[0] == t}
    for o in objs:
        if o not in have: miss[o] += 1
print("객체별 빠진 프레임 수", dict(miss))
# SAM 저장소
try:
    d = json.load(io.open(f"{V}/data/학습데이터/자동라벨/sam2/{CLIP}.json", encoding="utf-8"))
    fr = {k: v for k, v in d["frames"].items() if v}; print(f"\nSAM 저장소: 프레임 {len(fr)}, 씨앗 {len(d.get('seeds', []))}, updated {d.get('updated')}")
    per = collections.Counter(o for v in fr.values() for o in v); print("결과 객체별 프레임 수", dict(per))
    # 결과에서 두 객체가 같은 자리(IoU>0.6)인 프레임 수
    same = 0
    for k, v in fr.items():
        bs = list(v.values())
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                a, b = bs[i], bs[j]
                if iou([0] + a, [0] + b) > 0.6: same += 1
    print("결과에서 두 객체가 겹치는(IoU>0.6) 프레임-쌍 수", same)
    ks = sorted(fr, key=float)
    for k in ks[:: max(1, len(ks) // 10)]:
        print(" ", k, {o: round(b[0] + b[2] / 2, 3) for o, b in fr[k].items()})
except FileNotFoundError:
    print("\nSAM 저장소 파일 없음")

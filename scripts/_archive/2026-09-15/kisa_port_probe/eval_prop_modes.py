# -*- coding: utf-8 -*-
"""전파 방식 비교(요구사항 5): 화재 손라벨이 있는 클립에서 첫 손라벨 프레임을 참조샷으로 삼아 전파하고,
나머지 손라벨 프레임의 박스와 비교한다(IoU · 잡은 비율 · 프레임 간 넓이 흔들림).
방식: separate(객체별 세션, 기본) · separate_lowsmoke(연기 임계 -0.5) · joint(한 세션) · detect(프레임마다 DINO+SAM)
결과: _kisa_port/eval_prop_modes_<시각>.{json,md}. 서버 코드를 그대로 불러 쓴다(대시보드 서버와 별개 프로세스)."""
import sys, os, json, io, time, collections, statistics
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2")
os.chdir("/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2")
import serve_kisa as S

V = S.G
MAX_CLIPS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
MODES = {"separate": dict(mode="separate"), "separate_lowsmoke": dict(mode="separate", thr={1: 0.0, 2: -0.5}),
         "joint": dict(mode="joint"), "detect": dict(mode="detect")}

rows = S.read_json(S.label_file("fire"), [])
by = collections.defaultdict(lambda: collections.defaultdict(dict))   # stem → t → cls → box
for r in rows:
    if int(r.get("cls", -1)) < 0:
        continue
    by[S.Path(r["clip"]).stem][round(float(r["t"]), 1)][int(r["cls"])] = [r["x"], r["y"], r["w"], r["h"]]


def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1]); x2 = min(a[0] + a[2], b[0] + b[2]); y2 = min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / (a[2] * a[3] + b[2] * b[3] - inter or 1.0)


def clip_full(stem):
    for p in S.RAW.rglob(stem + ".mp4"):
        return str(p.relative_to(S.RAW).with_suffix("")).replace("\\", "/")
    return None


# 평가 대상: 불·연기 둘 다 3프레임 이상 손라벨된 클립(밀도 높은 것 우선)
cands = [(st, ts) for st, ts in by.items() if sum(1 for t in ts if 0 in ts[t]) >= 3 and sum(1 for t in ts if 1 in ts[t]) >= 3]
cands.sort(key=lambda x: -len(x[1]))
cands = cands[:MAX_CLIPS]
print(f"평가 클립 {len(cands)}개:", [c[0] for c in cands], flush=True)

res = {m: {"iou": {1: [], 2: []}, "hit": {1: [0, 0], 2: [0, 0]}, "jit": {1: [], 2: []}, "sec": 0.0, "per_clip": {}} for m in MODES}
for stem, ts in cands:
    cf = clip_full(stem)
    if not cf:
        print("영상 없음", stem); continue
    tl = sorted(ts)
    t_first = tl[0]
    seeds = [{"t": t_first, "obj": (2 if c == 1 else 1), "box": b} for c, b in ts[t_first].items()]
    a, b = t_first, tl[-1]
    for m, kw in MODES.items():
        tic = time.time()
        try:
            frames, polys, sec, err = S.sam2_propagate_objs(cf, seeds, step=1.0, a=a, b=b, **kw)
        except Exception as e:
            frames, err = {}, str(e)
        dt = time.time() - tic
        res[m]["sec"] += dt
        pc = {"err": err, "sec": round(dt, 1), "n_pred": len(frames)}
        for oid in (1, 2):
            cls = oid - 1
            for t in tl[1:]:
                if cls not in ts[t]:
                    continue
                res[m]["hit"][oid][1] += 1
                pb = (frames.get(f"{t:.1f}") or {}).get(str(oid))
                if pb:
                    res[m]["hit"][oid][0] += 1
                    res[m]["iou"][oid].append(iou(pb, ts[t][cls]))
                else:
                    res[m]["iou"][oid].append(0.0)
            areas = [v[str(oid)][2] * v[str(oid)][3] for k, v in sorted(frames.items(), key=lambda kv: float(kv[0])) if str(oid) in v]
            if len(areas) > 1:
                ma = statistics.mean(areas) or 1e-6
                res[m]["jit"][oid].append(statistics.mean(abs(x - y) for x, y in zip(areas, areas[1:])) / ma)
        res[m]["per_clip"][stem] = pc
        print(f"  {stem} {m:18s} {dt:5.1f}s 예측 {len(frames)}프레임 {err or ''}", flush=True)

out = {"clips": [c[0] for c in cands], "modes": {}}
lines = ["| 방식 | 불 IoU | 연기 IoU | 불 잡음 | 연기 잡음 | 불 흔들림 | 연기 흔들림 | 시간(s) |", "|---|---|---|---|---|---|---|---|"]
for m, r in res.items():
    mi = {o: (statistics.mean(r["iou"][o]) if r["iou"][o] else 0.0) for o in (1, 2)}
    hit = {o: (r["hit"][o][0] / r["hit"][o][1] if r["hit"][o][1] else 0.0) for o in (1, 2)}
    jit = {o: (statistics.mean(r["jit"][o]) if r["jit"][o] else 0.0) for o in (1, 2)}
    score = 0.5 * (mi[1] + mi[2]) - 0.1 * (jit[1] + jit[2])          # 종합: IoU 평균 - 흔들림 벌점
    out["modes"][m] = {"iou": mi, "hit": hit, "jitter": jit, "sec": round(r["sec"], 1), "score": round(score, 4), "per_clip": r["per_clip"]}
    lines.append(f"| {m} | {mi[1]:.3f} | {mi[2]:.3f} | {hit[1]:.0%} | {hit[2]:.0%} | {jit[1]:.2f} | {jit[2]:.2f} | {r['sec']:.0f} |")
best = max(out["modes"], key=lambda m: out["modes"][m]["score"])
out["best"] = best
stamp = time.strftime("%Y%m%d_%H%M")
od = V / "_kisa_port"
io.open(od / f"eval_prop_modes_{stamp}.json", "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
md = f"# 전파 방식 비교 {stamp}\n\n클립 {len(cands)}개(첫 손라벨 프레임만 참조샷, 이후 손라벨 프레임과 비교)\n\n" + "\n".join(lines) + f"\n\n종합 최고: **{best}** (IoU 평균 − 0.1×흔들림)\n"
io.open(od / f"eval_prop_modes_{stamp}.md", "w", encoding="utf-8").write(md)
print(md)

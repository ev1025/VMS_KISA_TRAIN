# -*- coding: utf-8 -*-
"""연기 전파가 왜 안 맞는지 본다: 첫 손라벨 프레임만 참조샷으로 전파하고, 이후 손라벨 프레임의 손 박스와 비교.
어긋나는 방식(너무 큼/작음/위치 이동)을 수치로 찍는다. 저장소에는 쓰지 않는다."""
import sys, os
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2")
os.chdir("/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2")
import serve_kisa as S

CLIP = sys.argv[1] if len(sys.argv) > 1 else "kisa_연구개발_방화영상/C050105_001"
stem = CLIP.split("/")[-1]
rows = [r for r in S.read_json(S.label_file("fire"), []) if S.Path(r["clip"]).stem == stem and int(r.get("cls", -1)) >= 0]
by = {}
for r in rows:
    by.setdefault(round(float(r["t"]), 1), {}).setdefault(int(r["cls"]), []).append([r["x"], r["y"], r["w"], r["h"]])
ts = sorted(by)
print(f"{stem} 손라벨 프레임 {len(ts)} · 구간 {ts[0]}~{ts[-1]}초")
t0 = ts[0]
seeds = [{"t": t0, "obj": (2 if c == 1 else 1), "box": b[0]} for c, b in by[t0].items()]
print("참조샷:", [(s["obj"], [round(v, 4) for v in s["box"]]) for s in seeds])
frames, polys, sec, err = S.sam2_propagate_objs(CLIP, seeds, step=1.0, a=t0, b=ts[-1], mode="separate")
print(f"전파 {len(frames)}프레임 · {sec}초 · 오류 {err}")


def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1]); x2 = min(a[0] + a[2], b[0] + b[2]); y2 = min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / (a[2] * a[3] + b[2] * b[3] - inter or 1.0)


print(f"{'시각':>7s} {'객체':>4s} {'손 넓이':>9s} {'예측 넓이':>9s} {'넓이비':>7s} {'IoU':>5s}  {'중심이동':>8s}")
for t in ts[1:]:
    for cls, hb in sorted(by[t].items()):
        oid = 2 if cls == 1 else 1
        pb = (frames.get(f"{t:.1f}") or {}).get(str(oid))
        h = hb[0]
        if not pb:
            print(f"{t:7.1f} {'연기' if oid == 2 else '불':>4s} {h[2] * h[3]:9.5f} {'없음':>9s}")
            continue
        d = ((pb[0] + pb[2] / 2) - (h[0] + h[2] / 2), (pb[1] + pb[3] / 2) - (h[1] + h[3] / 2))
        print(f"{t:7.1f} {'연기' if oid == 2 else '불':>4s} {h[2] * h[3]:9.5f} {pb[2] * pb[3]:9.5f} "
              f"{(pb[2] * pb[3]) / (h[2] * h[3] or 1e-9):7.2f} {iou(pb, h):5.2f}  {d[0]:+.3f},{d[1]:+.3f}")

# -*- coding: utf-8 -*-
"""Grounding DINO 가 연기를 잡는지 확인. 손라벨에 연기 박스가 있는 프레임에서 프롬프트·임계를 바꿔가며 검출 수와 IoU 를 본다."""
import sys, os
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2")
os.chdir("/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2")
import serve_kisa as S

PROMPTS = ["fire. flame. smoke.", "smoke.", "smoke plume. white smoke. gray smoke.",
           "smoke rising from fire.", "a cloud of smoke."]
THS = [0.25, 0.15, 0.08]

rows = [r for r in S.read_json(S.label_file("fire"), []) if int(r.get("cls", -1)) == 1]     # 연기 손라벨
by = {}
for r in rows:
    by.setdefault((S.Path(r["clip"]).stem, round(float(r["t"]), 1)), []).append([r["x"], r["y"], r["w"], r["h"]])
big = sorted(by.items(), key=lambda kv: -max(b[2] * b[3] for b in kv[1]))[:5]                # 연기가 큰 프레임 5개
print("검사 프레임:", [(k[0], k[1], round(max(b[2] * b[3] for b in v), 4)) for k, v in big])


def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1]); x2 = min(a[0] + a[2], b[0] + b[2]); y2 = min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / (a[2] * a[3] + b[2] * b[3] - inter or 1.0)


def clip_of(stem):
    for p in S.RAW.rglob(stem + ".mp4"):
        return str(p.relative_to(S.RAW).with_suffix("")).replace("\\", "/")
    return None


for prompt in PROMPTS:
    for th in THS:
        hit = tot = 0; best = []
        for (stem, t), hbs in big:
            cf = clip_of(stem)
            fr = S._frame_bgr(cf, t) if cf else None
            if fr is None:
                continue
            tot += 1
            h0, w0 = fr.shape[:2]
            dets = S.gdino_detect(fr, prompt, th)
            sm = [(sc, [x1 / w0, y1 / h0, (x2 - x1) / w0, (y2 - y1) / h0], lb) for sc, x1, y1, x2, y2, lb in dets if "smoke" in lb.lower() or "cloud" in lb.lower()]
            if sm:
                hit += 1
                best.append(round(max(iou(b, hbs[0]) for _, b, _ in sm), 2))
        print(f"{prompt:40s} th {th:.2f} → 연기 검출 {hit}/{tot} · IoU {best}")

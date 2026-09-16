# -*- coding: utf-8 -*-
"""GT 시각 프레임에 구역과 덤프 박스를 그린다. 미검 원인을 눈으로 가르려는 용도."""
import json
import sys
from pathlib import Path

import cv2

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K          # noqa: E402
import kisa_paths as KP         # noqa: E402

CFG = K.ITEMS["intrusion"]
DUMP = V / "dumps/intrusion_tile_v3"
OUT = Path("/tmp/zonecheck"); OUT.mkdir(exist_ok=True)

for stem in sys.argv[1:]:
    mp = KP.find_mp4(stem)
    cap = cv2.VideoCapture(str(mp))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (W, H))
    g = next(KP.videos("침입").rglob(stem + ".xml"), None)
    gt = (K.read_alarms(g) or [{}])[0].get("start_s")
    rows = {round(json.loads(l)["t"], 1): json.loads(l)["boxes"]
            for l in (DUMP / (stem + ".jsonl")).read_text().splitlines()}
    print(f"{stem}  영상 {W}x{H}  GT {gt}s  구역점 {poly}")

    for t in (gt, gt + 2.0, gt + 5.0):
        t = round(t * 2) / 2.0                       # 0.5초 격자
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, im = cap.read()
        if not ok:
            continue
        import numpy as np
        cv2.polylines(im, [np.array(poly, dtype=int)], True, (0, 255, 255), 2)
        for pid, conf, x1, y1, x2, y2 in rows.get(t, []):
            ins = K.entered((x1, y1, x2, y2), poly, CFG["corners"])
            col = (0, 220, 0) if (ins and conf >= CFG["conf"]) else ((0, 160, 255) if ins else (200, 200, 200))
            cv2.rectangle(im, (int(x1), int(y1)), (int(x2), int(y2)), col, 2)
            cv2.putText(im, f"{pid}:{conf:.2f}", (int(x1), max(12, int(y1) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
            cv2.circle(im, (int((x1 + x2) / 2), int(y2)), 4, col, -1)   # 발끝
        cv2.putText(im, f"{stem} t={t} GT={gt}", (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imwrite(str(OUT / f"{stem}_{t:06.1f}.jpg"), im)
    cap.release()
print("->", sorted(p.name for p in OUT.glob("*.jpg")))

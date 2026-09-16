# -*- coding: utf-8 -*-
"""손라벨 단독 모델이 영상 시작 10초에 배회 경보를 낸 편들. 무엇을 사람으로 봤나."""
import sys
from pathlib import Path

import cv2

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["loitering"]
W = V / "runs/person_kisa_only_s_20260911/yolo11s/weights/best.pt"
OUT = Path("/tmp/fp"); OUT.mkdir(exist_ok=True)
STEMS = sys.argv[1:] or ["C00_025_0001", "C00_045_0001", "C00_071_0001"]

from ultralytics import YOLO   # noqa: E402
m = YOLO(str(W))

for stem in STEMS:
    poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (1280, 720))
    cap = cv2.VideoCapture(str(KP.find_mp4(stem)))
    print(f"== {stem}  (배회는 전체프레임 @{CFG.get('track_imgsz',640)} · conf {CFG['conf']})")
    for t in (0.0, 2.0, 4.0, 6.0):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, im = cap.read()
        if not ok:
            continue
        r = m.predict(im, conf=0.20, imgsz=CFG.get("track_imgsz", 640), classes=[0],
                      verbose=False, device=0)[0]
        keep = []
        for b in r.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0]); c = float(b.conf)
            inz = K.entered((x1, y1, x2, y2), poly, CFG["corners"])
            if c >= CFG["conf"] and inz:
                keep.append((c, int(x1), int(y1), int(x2 - x1), int(y2 - y1)))
        print(f"   t={t:4.1f}  구역안 문턱통과 {len(keep)}개  {keep[:3]}")
        import numpy as np
        cv2.polylines(im, [np.array(poly, dtype=int)], True, (0, 255, 255), 2)
        for b in r.boxes:
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0]); c = float(b.conf)
            if c < 0.20:
                continue
            inz = K.entered((x1, y1, x2, y2), poly, CFG["corners"])
            col = (0, 0, 255) if (inz and c >= CFG["conf"]) else (160, 160, 160)
            cv2.rectangle(im, (x1, y1), (x2, y2), col, 2)
            cv2.putText(im, f"{c:.2f}", (x1, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
        cv2.putText(im, f"{stem} t={t}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imwrite(str(OUT / f"{stem}_{t:04.1f}.jpg"), im)
    cap.release()
print("->", OUT)

# -*- coding: utf-8 -*-
"""YOLO-World 교사가 base 미탐 프레임(야간IR·설경·비)의 불을 보는지 스모크 테스트."""
import cv2
from pathlib import Path
from ultralytics import YOLOWorld

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/data/원본데이터/kisa_배포_방화채점셋/videos")
CASES = [("C00_089_0001", 228), ("C00_146_0003", 129), ("C00_216_0003", 127),
         ("C00_272_0003", 148), ("C00_038_0006", 213)]   # 마지막은 정탐(대조군)

model = YOLOWorld("yolov8x-worldv2.pt")
model.set_classes(["fire", "flame", "smoke"])
print(f"{'클립':16s} {'t':>4s} | 검출 (클래스 conf)")
for stem, t in CASES:
    cap = cv2.VideoCapture(str(V / (stem + ".mp4")))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    for dt in (0, 5):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((t + dt) * fps))
        ok, fr = cap.read()
        if not ok:
            continue
        best = {}
        # 전체 + 중앙타일 (미탐이 크기 문제였던 것 반영)
        h, w = fr.shape[:2]
        for crop in (fr, fr[h//4:3*h//4, w//4:3*w//4]):
            r = model.predict(crop, conf=0.05, imgsz=640, verbose=False)[0]
            for b in r.boxes:
                name = r.names[int(b.cls)]
                best[name] = max(best.get(name, 0), float(b.conf))
        print(f"{stem:16s} {t+dt:4d} | " + (" ".join(f"{k} {v:.2f}" for k, v in sorted(best.items())) or "-"), flush=True)
    cap.release()

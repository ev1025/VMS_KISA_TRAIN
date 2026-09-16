# -*- coding: utf-8 -*-
"""RT-DETR(트랜스포머 탐지기) 화재 학습 — YOLO 아닌 아키텍처 1회 검증. 24k, 640."""
import sys
from ultralytics import RTDETR

data, out_dir, name = sys.argv[1], sys.argv[2], sys.argv[3]
model = RTDETR("rtdetr-l.pt")                 # COCO 사전학습 RT-DETR-L
model.train(data=data, imgsz=640, epochs=60, batch=48, device=0,
            project=out_dir, name=name, exist_ok=True, plots=False,
            optimizer="AdamW", lr0=1e-4, warmup_epochs=3)

# -*- coding: utf-8 -*-
"""연구개발 방화영상의 GT 시각이 맞는지 확인한다.

배포 가중치로 클립 전체를 훑어 불 신뢰도 곡선을 만들고,
불이 처음 올라오는 시각과 XML 의 StartTime 을 비교한다.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

D = V / "data/원본데이터/kisa_연구개발_방화영상"
STRIDE = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
CLIPS = sys.argv[2:] or ["C050105_004", "C050205_004", "C050305_004"]

from ultralytics import YOLO   # noqa: E402
CFG = K.ITEMS["fire"]
MODELS = [(YOLO(str(p)), z) for p, z in K.fire_weights(CFG)]


def hms(s):
    return f"{int(s)//60:02d}:{int(s)%60:02d}"


def gt_of(stem):
    r = ET.parse(D / (stem + ".xml")).getroot()
    h, m, s = (int(x) for x in r.find(".//StartTime").text.split(":"))
    return h * 3600 + m * 60 + s


for stem in CLIPS:
    gt = gt_of(stem)
    cap = cv2.VideoCapture(str(D / (stem + ".mp4")))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = n / fps
    print(f"== {stem}  길이 {hms(dur)}  XML GT {hms(gt)} ({gt}s)")
    curve = []
    t = 0.0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, im = cap.read()
        if not ok:
            break
        h, w = im.shape[:2]
        crops = [im] + [im[y:y + h // 2, x:x + w // 2] for x, y in
                        ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
        best = 0.0
        for model, z in MODELS:
            for c in crops:
                for b in model.predict(c, conf=0.05, imgsz=z, verbose=False, device=0)[0].boxes:
                    if K.FIRE_NAMES.get(int(b.cls)) == "fire":
                        best = max(best, float(b.conf))
        curve.append((round(t, 1), round(best, 3)))
        t += STRIDE
    cap.release()

    first = next((t for t, c in curve if c >= CFG["fire"]), None)
    print(f"   불 {CFG['fire']} 처음 넘는 시각: {'없음' if first is None else f'{hms(first)} ({first}s)'}"
          f"   XML 과 차이 {'-' if first is None else f'{first - gt:+.0f}초'}")
    hi = [f"{hms(t)}:{c:.2f}" for t, c in curve if c >= 0.2]
    print(f"   0.2 넘는 구간({len(hi)}개): {' '.join(hi[:24])}")
    print()

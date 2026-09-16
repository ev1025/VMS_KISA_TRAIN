# -*- coding: utf-8 -*-
"""배포 앙상블이 그 시각에 무엇을 불로 봤는지 상자를 그린다(6뷰 낱장, 배포와 같은 경로)."""
import sys
from pathlib import Path

import cv2
import numpy as np

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402
from ultralytics import YOLO   # noqa: E402

C = K.ITEMS["fire"]
MODELS = [(YOLO(str(p)), z, Path(p).name) for p, z in K.fire_weights(C)]
stem = sys.argv[1]
times = [float(x) for x in sys.argv[2:]]
cap = cv2.VideoCapture(str(KP.find_mp4(stem)))
OUT = Path("/tmp/firebox"); OUT.mkdir(exist_ok=True)

for t in times:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
    ok, im = cap.read()
    if not ok:
        continue
    h, w = im.shape[:2]
    # 원본에서 잘라 두고, 그림은 사본에만 그린다.
    # (잘라낸 것은 원본을 가리키는 view 라, 원본에 상자를 그리면 다음 모델 입력이 오염된다.
    #  실제로 그 탓에 123.0초가 0.477 대신 0.218 로 나왔다. 2026-09-16)
    src = im.copy()
    views = [(src, 0, 0)] + [(src[y:y + h // 2, x:x + w // 2], x, y) for x, y in
                            ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
    best = 0.0
    for model, z, name in MODELS:
        for crop, ox, oy in views:
            for b in model.predict(crop, conf=0.05, imgsz=z, verbose=False, device=0)[0].boxes:
                if K.FIRE_NAMES.get(int(b.cls)) != "fire":
                    continue
                cf = float(b.conf)
                if cf < 0.15:
                    continue
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                col = (0, 0, 255) if cf >= C["fire"] else (0, 165, 255)
                cv2.rectangle(im, (int(x1 + ox), int(y1 + oy)), (int(x2 + ox), int(y2 + oy)), col, 2)
                cv2.putText(im, f"{cf:.2f} {name[:9]}", (int(x1 + ox), max(14, int(y1 + oy) - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
                best = max(best, cf)
    cv2.putText(im, f"{stem} t={t}s  fire max {best:.3f}", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.imwrite(str(OUT / f"{stem}_{t:06.1f}.jpg"), im)
    print(f"  t={t}  최고 {best:.3f}")
cap.release()

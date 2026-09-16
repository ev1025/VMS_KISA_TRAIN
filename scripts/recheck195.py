# -*- coding: utf-8 -*-
"""덤프가 지금 다시 돌려도 같은 값을 내는지 확인한다.

프레임을 어떻게 꺼내느냐로 값이 달라질 수 있다.
  seek  : cap.set(POS_MSEC) 로 건너뛴다. 키프레임 기준이라 정확히 그 프레임이 아닐 수 있다
  순차  : grab() 으로 전부 넘기며 필요한 것만 retrieve. 배포(FileSource)와 같은 방식
"""
import json
import sys
from pathlib import Path

import cv2

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402
from ultralytics import YOLO   # noqa: E402

C = K.ITEMS["fire"]
MODELS = [(YOLO(str(p)), z) for p, z in K.fire_weights(C)]
stem, LO, HI = "C00_195_0001", 108.0, 132.0


def fire_conf(im):
    h, w = im.shape[:2]
    crops = [im] + [im[y:y + h // 2, x:x + w // 2] for x, y in
                    ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
    best = 0.0
    for model, z in MODELS:
        for c in crops:
            for b in model.predict(c, conf=0.05, imgsz=z, verbose=False, device=0)[0].boxes:
                if K.FIRE_NAMES.get(int(b.cls)) == "fire":
                    best = max(best, float(b.conf))
    return best


mp4 = KP.find_mp4(stem)
dump = {round(t, 1): f for t, f, s in
        json.load(open(V / "dumps/score_tl/_deploy.json", encoding="utf-8"))[stem]["rows"]}

# 순차 디코드 (배포 FileSource 와 같다)
cap = cv2.VideoCapture(str(mp4))
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
step = max(1, int(round(fps * C["stride"])))
seq = {}
i = 0
while True:
    if not cap.grab():
        break
    t = i / fps
    if i % step == 0 and LO <= t <= HI:
        ok, fr = cap.retrieve()
        if ok:
            seq[round(t, 1)] = fire_conf(fr)
    i += 1
    if t > HI:
        break
cap.release()

# seek 디코드
cap = cv2.VideoCapture(str(mp4))
sk = {}
for t in sorted(seq):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
    ok, fr = cap.read()
    if ok:
        sk[t] = fire_conf(fr)
cap.release()

print(f"{stem}   문턱 {C['fire']}")
print(f"{'t':>7}{'덤프':>8}{'순차':>8}{'seek':>8}   적중(덤프/순차/seek)")
for t in sorted(seq):
    d, q, s = dump.get(t, float('nan')), seq[t], sk.get(t, float('nan'))
    m = "".join("O" if v >= C["fire"] else "." for v in (d, q, s))
    flag = "  <-- 다름" if (d >= C["fire"]) != (q >= C["fire"]) else ""
    print(f"{t:>7.1f}{d:>8.3f}{q:>8.3f}{s:>8.3f}   {m}{flag}")

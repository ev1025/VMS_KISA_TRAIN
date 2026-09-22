# -*- coding: utf-8 -*-
"""합성 안개가 모델에 주는 열화가 실제 안개(채점 195)의 열화와 닮았는지 잰다. 추론은 표본 몇백 장만(GPU 2GB 안).

읽는 법: 맑은 표본에서 불 신뢰도가 높고, 합성 안개에서 195 편 수준으로 무너지면 '같은 열화' 다.
         195 는 채점 편이라 여기서 비교만 하고 학습·튜닝에는 쓰지 않는다.
사용: python scripts/fog_probe_eval.py <probe폴더> <가중치.pt> <imgsz>
"""
import glob
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import kisa_paths as KP   # noqa: E402

probe, w, imgsz = sys.argv[1], sys.argv[2], int(sys.argv[3])
model = YOLO(w)


def max_fire(img):
    r = model.predict(img, imgsz=imgsz, conf=0.05, verbose=False, half=True, device=0)[0]
    best = 0.0
    for b in r.boxes:
        if int(b.cls) == 0:
            best = max(best, float(b.conf))
    return best


def summ(name, vals):
    vals = sorted(vals)
    if not vals:
        print("  %-22s 표본 없음" % name); return
    n = len(vals)
    print("  %-22s %3d장 | 불 최대신뢰도 중앙 %.2f · 상위25%% %.2f | 0.40 이상 %3.0f%% | 0.25 이상 %3.0f%%"
          % (name, n, vals[n // 2], vals[3 * n // 4], 100.0 * sum(v >= 0.40 for v in vals) / n, 100.0 * sum(v >= 0.25 for v in vals) / n))


print("가중치 %s @%d" % (Path(w).parent.parent.parent.name if "runs" in w else Path(w).name, imgsz))
for lv in ("clear", "mild", "light", "heavy"):
    files = sorted(glob.glob(str(Path(probe) / lv / "*.jpg")))
    summ("합성 " + lv, [max_fire(cv2.imread(f)) for f in files])


def clip_vals(stem, t0, t1, step=2):
    cap = cv2.VideoCapture(str(KP.find_mp4(stem))); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    out = []
    for t in range(t0, t1 + 1, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps)); ok, fr = cap.read()
        if ok:
            out.append(max_fire(fr))
    return out


print("  --- 채점 편(비교만): 정답 뒤 0~16초 구간 = 불이 실제로 있는 구간")
summ("195 안개 (114~130s)", clip_vals("C00_195_0001", 114, 130))
summ("216 눈 (122~138s)", clip_vals("C00_216_0003", 122, 138))
summ("272 야간눈 (123~139s)", clip_vals("C00_272_0003", 123, 139))
summ("012 맑음 (224~240s)", clip_vals("C00_012_0007", 224, 240))

# -*- coding: utf-8 -*-
"""배회 경로(BoT-SORT 전체 프레임)의 NMS 설정 점검: 겹친 박스가 모델 탓인가, 입력 크기 탓인가, NMS 문턱 탓인가.

왜 (2026-09-18)
    손라벨 모델 배회 덤프의 겹친 박스 비율이 35% 로 배포 모델(13%)의 3배다(dup_stats.py).
    학습 라벨에는 겹친 박스가 0.2% 뿐이라 라벨을 배운 것이 아니다. 남는 후보는
    (1) 입력 크기(배포 640 vs 손라벨 1280) (2) ultralytics 기본 NMS iou=0.7 (3) 모델 자체.
    세 축을 바꿔 가며 같은 편들을 다시 돌려 겹친 박스 쌍을 센다. 채점용 덤프는 만들지 않는다(가벼운 점검).

사용
    python scripts/nms_probe.py [--clips C00_211_0002,...] [--stride 1.0]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import kisa_paths as KP   # noqa: E402

CLIPS = ["C00_211_0002", "C00_232_0001", "C00_260_0002", "C00_013_0001", "C00_024_0001"]
MODELS = [("배포 person_v2", V / "_kisa_port/weights/kisa/person_v2.pt"),
          ("손라벨 32.6%", "results/p1280_coco_hand_20260917"),
          ("손라벨 10.8%", "results/p1280_ov2_20260917")]


def weights(spec):
    p = Path(spec)
    if p.suffix == ".pt":
        return p
    return Path(json.loads((V / spec / "meta.json").read_text(encoding="utf-8"))["best_pt"])


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def pair_kind(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    if i <= 0:
        return None
    if i / (area(a) + area(b) - i) >= 0.3:
        return "iou"
    if i / max(1e-6, min(area(a), area(b))) >= 0.6:
        return "contain"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default=",".join(CLIPS))
    ap.add_argument("--stride", type=float, default=1.0)
    a = ap.parse_args()
    clips = a.clips.split(",")
    vids = [next(KP.videos("배회").rglob(c + ".mp4")) for c in clips]
    print("%-14s %5s %4s %7s %9s %7s %7s  %s" % ("모델", "imgsz", "iou", "표본", "박스/표본", "IoU쌍", "포함쌍", "겹친 박스 비율(conf>=0.4)"), flush=True)
    for label, spec in MODELS:
        w = weights(spec)
        for imgsz in (640, 1280):
            for iou_th in (0.7, 0.5):
                model = YOLO(str(w))
                frames = boxes = k_iou = k_con = 0
                t0 = time.time()
                for mp4 in vids:
                    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
                    step = max(1, round(fps * a.stride)); i = 0
                    while True:
                        if not cap.grab():
                            break
                        if i % step == 0:
                            ok, fr = cap.retrieve()
                            if ok:
                                r = model.track(fr, persist=True, conf=0.20, iou=iou_th, imgsz=imgsz, classes=[0],
                                                verbose=False, tracker="botsort.yaml")[0]
                                bs = []
                                if r.boxes is not None:
                                    for b in r.boxes:
                                        if float(b.conf) >= 0.40:
                                            bs.append([float(v) for v in b.xyxy[0]])
                                frames += 1; boxes += len(bs)
                                for x in range(len(bs)):
                                    for y in range(x + 1, len(bs)):
                                        k = pair_kind(bs[x], bs[y]); k_iou += k == "iou"; k_con += k == "contain"
                        i += 1
                    cap.release()
                print("%-14s %5d %4.1f %7d %9.2f %7d %7d  %.1f%%   (%.0f초)" % (
                    label, imgsz, iou_th, frames, boxes / max(1, frames), k_iou, k_con,
                    100.0 * (k_iou + k_con) / max(1, boxes), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""트랙 덤프: botsort ID 포함 (t, [[id,conf,x1,y1,x2,y2],...]). GSI 평활 스윕용.

--imgsz · --iou (2026-09-18 추가): 제출 도구 BotSortPersons 는 입력 크기만 바꾸고 NMS 는 ultralytics 기본(iou 0.7)이다.
    손라벨 모델은 1280 입력에서 한 사람에 박스가 2~3개 나와(부분 박스) 트랙이 갈라진다. NMS 문턱을 바꿔 덤프를 다시 떠서
    같은 판정기로 점수를 비교하려고 인자로 뺐다. 기본값(640 · 0.7)은 예전 덤프와 같다.
"""
import argparse
import json
import time
from pathlib import Path

import cv2
from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=float, default=1.0)
    ap.add_argument("--conf", type=float, default=0.10)
    ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--iou", type=float, default=0.7, help="NMS IoU 문턱(ultralytics 기본 0.7)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(a.model)
    vids = sorted(Path(a.videos).glob("*.mp4"))
    for order, mp4 in enumerate(vids, 1):
        t0 = time.time()
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps * a.stride))
        rows = []
        i = 0
        while True:
            if not cap.grab():
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    boxes = []
                    if getattr(a, 'tiles', False):
                        # 타일: track 대신 detect 6뷰, id 는 -1 (규칙에서 트랙 불필요한 채점용)
                        h, w = fr.shape[:2]
                        regions = [(0,0,w,h)] + [(x,y,w//2,h//2) for x,y in ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4))]
                        for ox,oy,rw,rh in regions:
                            for b_ in model.predict(fr[oy:oy+rh, ox:ox+rw], conf=a.conf, imgsz=640, classes=[0], verbose=False)[0].boxes:
                                x1,y1,x2,y2 = (float(v) for v in b_.xyxy[0])
                                boxes.append([-1, round(float(b_.conf),3), round(x1+ox), round(y1+oy), round(x2+ox), round(y2+oy)])
                    else:
                        r = model.track(fr, persist=True, conf=a.conf, iou=a.iou, imgsz=a.imgsz, classes=[0],
                                        verbose=False, tracker="botsort.yaml")[0]
                        if r.boxes.id is not None:
                            for b_ in r.boxes:
                                x1, y1, x2, y2 = (round(float(v)) for v in b_.xyxy[0])
                                boxes.append([int(b_.id), round(float(b_.conf), 3), x1, y1, x2, y2])
                    rows.append({"t": round(i / fps, 2), "boxes": boxes})
            i += 1
        cap.release()
        if hasattr(model, "predictor") and model.predictor is not None:
            model.predictor = None            # 영상 간 트랙 ID 오염 방지
        with open(out / (mp4.stem + ".jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"[{order}/{len(vids)}] {mp4.stem} 표본 {len(rows)} ({time.time()-t0:.0f}초)", flush=True)


if __name__ == "__main__":
    main()

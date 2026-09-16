# -*- coding: utf-8 -*-
"""방화 시계열 피처 추출 (딥리서치 1번): 프레임별 타일 conf + 플리커 + optical flow → 1D 벡터.

대상: 방화75(학습, 시각GT) + 배포10(검증). base 모델 6뷰 타일, 0.5초 간격.
피처(프레임당 20차원):
  [6뷰 fire max conf(6), 6뷰 smoke max conf(6), 전체최대 fire박스 cx,cy,w,h(4),
   플리커 에너지(1: 1~10Hz 대역 휘도 시간미분), flow 분산(2: 크기·방향)] = 19 → 20 패딩
플리커/flow 는 직전 프레임과의 차분이라 시퀀스 순서대로 계산.
"""
import argparse
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

VIEWS = None  # 아래에서 프레임 크기로 계산


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def gt_info(xml_path):
    try:
        al = ET.parse(xml_path).getroot().find(".//Alarm")
        if al is None:
            return -1.0, 0.0
        return float(hms(al.findtext("StartTime"))), float(hms(al.findtext("AlarmDuration")) or 10)
    except Exception:
        return -1.0, 0.0


def tiles(fr):
    h, w = fr.shape[:2]
    regions = [(0, 0, w, h)] + [(x, y, w // 2, h // 2) for x, y in
               ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
    return regions


def frame_feat(model, fr, prev_gray, roi_hist):
    """20차원 피처 + 갱신된 prev_gray."""
    h, w = fr.shape[:2]
    gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    view_fire = [0.0] * 6
    view_smoke = [0.0] * 6
    best_box = [0.0, 0.0, 0.0, 0.0]
    best_conf = 0.0
    for vi, (ox, oy, rw, rh) in enumerate(tiles(fr)):
        r = model.predict(fr[oy:oy + rh, ox:ox + rw], conf=0.10, imgsz=640, verbose=False)[0]
        for b in r.boxes:
            cls = r.names[int(b.cls)]
            cf = float(b.conf)
            if cls == "fire":
                view_fire[vi] = max(view_fire[vi], cf)
                if cf > best_conf:
                    best_conf = cf
                    x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                    best_box = [(x1 + x2) / 2 / rw, (y1 + y2) / 2 / rh, (x2 - x1) / rw, (y2 - y1) / rh]
            elif cls == "smoke":
                view_smoke[vi] = max(view_smoke[vi], cf)
    # 플리커: 밝은 영역(>200) 픽셀의 프레임간 휘도 변화량 (움직이는 고휘도 = 화염 후보)
    flicker = 0.0
    flow_mag = flow_dir = 0.0
    if prev_gray is not None:
        bright = gray > 200
        if bright.any():
            flicker = float(np.abs(gray[bright].astype(np.int16) - prev_gray[bright].astype(np.int16)).mean()) / 255
        # optical flow 분산 (축소본에서 빠르게)
        small = cv2.resize(gray, (160, 90))
        psmall = cv2.resize(prev_gray, (160, 90))
        flow = cv2.calcOpticalFlowFarneback(psmall, small, None, 0.5, 2, 15, 2, 5, 1.1, 0)
        mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        m = mag > 0.5
        if m.any():
            flow_mag = float(mag[m].std())
            ang = np.arctan2(flow[..., 1], flow[..., 0])[m]
            flow_dir = float(np.std(ang))
    feat = view_fire + view_smoke + best_box + [flicker, flow_mag, flow_dir]
    feat = (feat + [0.0])[:20]
    return np.array(feat, np.float32), gray


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, nargs="+")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=float, default=0.5)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(a.model)
    vids = []
    for d in a.videos:
        vids += sorted(Path(d).glob("*.mp4"))
    for order, mp4 in enumerate(vids, 1):
        dst = out / (mp4.stem + ".npz")
        if dst.exists():
            continue
        start, dur = gt_info(mp4.with_suffix(".xml"))
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps * a.stride))
        ts, feats = [], []
        prev = None
        i = 0
        while True:
            if not cap.grab():
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    f, prev = frame_feat(model, fr, prev, None)
                    ts.append(i / fps)
                    feats.append(f)
            i += 1
        cap.release()
        np.savez_compressed(dst, t=np.array(ts, np.float32),
                            x=np.stack(feats) if feats else np.zeros((0, 20), np.float32),
                            gt_start=start, gt_dur=dur)
        if order % 10 == 0 or order == len(vids):
            print(f"[{order}/{len(vids)}] {mp4.stem} 표본 {len(ts)}", flush=True)
    print("완료")


if __name__ == "__main__":
    main()

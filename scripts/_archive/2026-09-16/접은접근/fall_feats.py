# -*- coding: utf-8 -*-
"""쓰러짐 시계열 학습용 1D 피처 추출 (제미나이 플랜 Day3).

대상: 해외환경 쓰러짐 330편(학습, 시각 GT) + 배포용 10편(검증).
x-pose 로 0.5초 간격 프레임당 대표 person 의 피처 벡터를 뽑아 npz 저장.
피처(프레임당 1인 기준, 최고 conf person):
  [conf, cx, cy, w, h, 종횡비, 몸통각(도), 어깨중점y/H, 17kpt(x,y,c)...] = 8 + 51 = 59차원
사람 없으면 0 벡터 (시간축 유지, 제로패딩 방침).
"""
import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def gt_info(xml_path):
    try:
        al = ET.parse(xml_path).getroot().find(".//Alarm")
        if al is None:
            return None, None
        return hms(al.findtext("StartTime")), hms(al.findtext("AlarmDuration")) or 10
    except Exception:
        return None, None


def frame_feat(r, W, H):
    if r.keypoints is None or not len(r.boxes):
        return np.zeros(59, np.float32)
    bi = int(np.argmax([float(b.conf) for b in r.boxes]))
    b = r.boxes[bi]
    kp = r.keypoints.data.cpu().numpy()[bi]        # (17,3)
    x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
    w, h = x2 - x1, y2 - y1
    sh = [(kp[i][0], kp[i][1]) for i in (5, 6) if kp[i][2] >= 0.2]
    hip = [(kp[i][0], kp[i][1]) for i in (11, 12) if kp[i][2] >= 0.2]
    angle = 90.0
    neck_y = 0.0
    if sh:
        neck_y = sum(p[1] for p in sh) / len(sh) / H
    if sh and hip:
        sx = sum(p[0] for p in sh) / len(sh)
        sy = sum(p[1] for p in sh) / len(sh)
        hx = sum(p[0] for p in hip) / len(hip)
        hy = sum(p[1] for p in hip) / len(hip)
        a = abs(math.degrees(math.atan2(hy - sy, hx - sx)))
        angle = min(a, 180 - a)
    base = [float(b.conf), (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, w / W, h / H,
            w / max(1, h), angle / 90.0, neck_y]
    kflat = []
    for i in range(17):
        kflat += [kp[i][0] / W, kp[i][1] / H, float(kp[i][2])]
    return np.array(base + kflat, np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=float, default=0.5)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO("yolo11x-pose.pt")
    vids = []
    for d in a.videos:
        vids += sorted(Path(d).rglob("*.mp4"))
    for order, mp4 in enumerate(vids, 1):
        dst = out / (mp4.stem + ".npz")
        if dst.exists():
            continue
        start, dur = gt_info(mp4.with_suffix(".xml"))
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps * a.stride))
        ts, feats = [], []
        i = 0
        while True:
            if not cap.grab():
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    H, W = fr.shape[:2]
                    r = model.predict(fr, conf=0.15, imgsz=640, verbose=False)[0]
                    ts.append(i / fps)
                    feats.append(frame_feat(r, W, H))
            i += 1
        cap.release()
        np.savez_compressed(dst, t=np.array(ts, np.float32),
                            x=np.stack(feats) if feats else np.zeros((0, 59), np.float32),
                            gt_start=-1.0 if start is None else float(start),
                            gt_dur=0.0 if dur is None else float(dur))
        if order % 20 == 0 or order == len(vids):
            print(f"[{order}/{len(vids)}] {mp4.stem} 표본 {len(ts)}", flush=True)
    print("완료")


if __name__ == "__main__":
    main()

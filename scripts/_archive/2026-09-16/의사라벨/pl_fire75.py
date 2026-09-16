# -*- coding: utf-8 -*-
"""방화75 실영상 의사라벨: base 모델 + 타일 추론으로 GT 이벤트 구간에 fire/smoke 박스 생성.

GT(F1 방식)엔 시각만 있고 박스가 없어, base+타일(작은 물체 복구)로 박스를 만든다.
- 이벤트 구간(GT시작-2 ~ +지속, 최대 60초)만 1초 간격, 영상당 상한
- 배경 네거티브: 점화 한참 전 프레임 5장(빈 라벨)
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
from ultralytics import YOLO


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def gt_event(xml):
    al = ET.parse(xml).getroot().find(".//Alarm")
    if al is None:
        return None, None
    start = hms(al.findtext("StartTime"))
    dur = hms(al.findtext("AlarmDuration")) or 30
    return start, min(dur, 60)


def infer_tiled(model, frame, conf):
    h, w = frame.shape[:2]
    regions = [(0, 0, w, h)] + [(x, y, w // 2, h // 2) for x, y in
               ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
    out = []
    for ox, oy, rw, rh in regions:
        r = model.predict(frame[oy:oy + rh, ox:ox + rw], conf=conf, imgsz=640, verbose=False)[0]
        for b in r.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            out.append((int(b.cls), float(b.conf), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
    return out


def nms(dets, iou_th=0.5):
    kept = []
    for cls in (0, 1):
        boxes = sorted([d for d in dets if d[0] == cls], key=lambda d: -d[1])
        while boxes:
            best = boxes.pop(0)
            kept.append(best)
            rem = []
            for d in boxes:
                xa, ya = max(best[2], d[2]), max(best[3], d[3])
                xb, yb = min(best[4], d[4]), min(best[5], d[5])
                inter = max(0, xb - xa) * max(0, yb - ya)
                a1 = (best[4] - best[2]) * (best[5] - best[3])
                a2 = (d[4] - d[2]) * (d[5] - d[3])
                if inter / (a1 + a2 - inter + 1e-6) < iou_th:
                    rem.append(d)
            boxes = rem
    return kept


def save(out, img, dets, stem):
    h, w = img.shape[:2]
    cv2.imwrite(str(out / "images" / (stem + ".jpg")), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    lines = [f"{c} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}"
             for c, _, x1, y1, x2, y2 in dets]
    (out / "labels" / (stem + ".txt")).write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--stride", type=float, default=1.0)
    ap.add_argument("--max-frames", type=int, default=60)
    a = ap.parse_args()

    out = Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    model = YOLO(a.model)
    total_pos = total_neg = 0
    for xml in sorted(Path(a.videos).glob("*.xml")):
        stem = xml.stem
        mp4 = xml.with_suffix(".mp4")
        if not mp4.exists():
            continue
        start, dur = gt_event(xml)
        if start is None:
            continue
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        pos = 0
        t = start - 2.0
        while t <= start + dur and pos < a.max_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, fr = cap.read()
            if ok:
                dets = nms(infer_tiled(model, fr, a.conf))
                if dets:
                    save(out, fr, dets, f"{stem}_ev{int(t)}")
                    pos += 1
            t += a.stride
        neg = 0
        for bt in (10, 30, 60, start - 60, start - 30):
            bt = max(5, min(bt, start - 10))
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(bt * fps))
            ok, fr = cap.read()
            if ok:
                save(out, fr, [], f"{stem}_bg{int(bt)}")
                neg += 1
        cap.release()
        total_pos += pos
        total_neg += neg
        print(f"{stem}: 라벨 {pos} · 배경 {neg}", flush=True)
    print(f"합계: 라벨 {total_pos} · 배경 {total_neg}")


if __name__ == "__main__":
    main()

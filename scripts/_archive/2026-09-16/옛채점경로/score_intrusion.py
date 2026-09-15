# -*- coding: utf-8 -*-
"""침입 30편 서버 채점기 (자립형): person 모델 + 발끝∈구역 + 창 규칙 → F1.

로컬 proto_intrusion 과 같은 규칙. GPU 라 전체/타일 둘 다 빠르게 돈다.
"""
import argparse
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import cv2
from ultralytics import YOLO

BEFORE, AFTER = 2.0, 10.0


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(xml):
    al = ET.parse(xml).getroot().find(".//Alarm")
    return hms(al.findtext("StartTime")) if al is not None else None


def zone(maps, stem):
    loc = "_".join(stem.split("_")[:2])
    r = ET.parse(Path(maps) / (loc + ".map")).getroot().find("Intrusion")
    return [tuple(map(int, p.text.split(","))) for p in r.findall("Point")]


def in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def foot_in_zone(model, frame, poly, conf, tiled, mode="full"):
    h, w = frame.shape[:2]
    regions = [(0, 0, w, h)]
    if tiled:
        regions += [(x, y, w // 2, h // 2) for x, y in
                    ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
    for ox, oy, rw, rh in regions:
        for b in model.predict(frame[oy:oy + rh, ox:ox + rw], conf=conf, imgsz=640,
                               classes=[0], verbose=False)[0].boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            x1, y1, x2, y2 = x1 + ox, y1 + oy, x2 + ox, y2 + oy
            if mode == "full":     # 몸 전체 진입 (스윕 LOOCV 69.09 확정 규칙)
                if all(in_poly(px, py, poly) for px, py in
                       ((x1, y1), (x2, y1), (x1, y2), (x2, y2))):
                    return True
            elif in_poly((x1 + x2) / 2, y2, poly):
                return True
    return False


def onset(model, mp4, poly, conf, stride, window, hits, tiled, mode="full"):
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps * stride))
    win = deque(maxlen=window)
    i = 0
    got = None
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                win.append((i / fps, foot_in_zone(model, fr, poly, conf, tiled, mode)))
                if sum(1 for _, h in win if h) >= hits:
                    got = next(t for t, h in win if h)
                    break
        i += 1
    cap.release()
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--videos", required=True)
    ap.add_argument("--maps", required=True)
    ap.add_argument("--conf", type=float, default=0.40)
    ap.add_argument("--stride", type=float, default=1.0)
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--hits", type=int, default=2)
    ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--mode", default="full", choices=["full", "foot"])
    a = ap.parse_args()

    model = YOLO(a.model)
    tp = fn = fp = 0
    for mp4 in sorted(Path(a.videos).glob("*.mp4")):
        stem = mp4.stem
        gt = gt_start(mp4.with_suffix(".xml"))
        o = onset(model, mp4, zone(a.maps, stem), a.conf, a.stride, a.window, a.hits, a.tiles, a.mode)
        if o is None:
            mark = "미검출"
            if gt is not None:
                fn += 1
        elif gt is not None and gt - BEFORE <= o <= gt + AFTER:
            mark = f"정검 {o:.0f}/{gt}"
            tp += 1
        else:
            mark = f"오검 {o:.0f}/{gt}"
            fp += 1
            if gt is not None:
                fn += 1
        print(f"  {stem}: {mark}", flush=True)
    r = tp / (tp + fn) if tp + fn else 0
    p = tp / (tp + fp) if tp + fp else 0
    f1 = 2 * r * p / (r + p) * 100 if r + p else 0
    print(f"[{a.tag}] 정검 {tp} 미검 {fn} 오검 {fp} → 점수 {f1:.2f}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""못 잡는 방화 영상에 타일 방식·해상도를 바꿔가며 불이 실제로 잡히는지 시험.

배경: 배포 10편 중 3편을 어떤 모델로도 못 잡는데, 프레임을 직접 보니
  C00_216 = 눈밭 위 40x27 픽셀 작은 불꽃, C00_195 = 짙은 안개, C00_012 = 신호가 9초 늦음.
현재 채점기의 타일은 2x2 + 중앙 5장뿐이라 작은 불이 640 입력에서 더 작아진다.
여기서는 겹치는 격자 타일과 입력 해상도를 조합해, 정답 시각 부근에서 불 신뢰도가 오르는지만 본다.
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

W = Path("/NHNHOME/WORKSPACE/26mss002_E3")
VID = W / "vms/data/원본데이터/kisa_배포_방화채점셋/videos"
GT = W / "vms/data/원본데이터/kisa_배포_방화채점셋/gt"


def gt_start(s):
    r = ET.parse(GT / f"{s}.xml").getroot().find(".//Alarm")
    h, m, sec = r.findtext("StartTime").split(":")
    return int(h) * 3600 + int(m) * 60 + int(sec)


def tiles_of(fr, grid, overlap):
    """겹치는 격자 타일. grid=1 이면 원본 한 장."""
    h, w = fr.shape[:2]
    if grid <= 1:
        return [fr]
    out = []
    th, tw = h // grid, w // grid
    oy, ox = int(th * overlap), int(tw * overlap)
    for gy in range(grid):
        for gx in range(grid):
            y0 = max(0, gy * th - oy); y1 = min(h, (gy + 1) * th + oy)
            x0 = max(0, gx * tw - ox); x1 = min(w, (gx + 1) * tw + ox)
            out.append(fr[y0:y1, x0:x1])
    return out


def scan(model, stem, mode, stride, span):
    """정답 시각 앞뒤 span 초 구간만 훑어 (불 최대, 연기 최대) 반환."""
    grid, overlap, imgsz, keep_full = mode
    g = gt_start(stem)
    cap = cv2.VideoCapture(str(VID / f"{stem}.mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    t0 = max(0.0, g - span)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t0 * fps))
    step = max(1, round(fps * stride))
    i = 0
    best_f = best_s = 0.0
    at_f = None
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = t0 + i / fps
        if t > g + span:
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                crops = tiles_of(fr, grid, overlap)
                if keep_full and grid > 1:
                    crops = [fr] + crops
                for c in crops:
                    r = model.predict(c, conf=0.03, verbose=False, imgsz=imgsz)[0]
                    for b in r.boxes:
                        cf = float(b.conf)
                        if int(b.cls) == 0:
                            if cf > best_f:
                                best_f, at_f = cf, round(t, 1)
                        else:
                            best_s = max(best_s, cf)
        i += 1
    cap.release()
    return best_f, best_s, at_f, g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--stems", nargs="+", default=["C00_216_0003", "C00_195_0001", "C00_012_0007"])
    ap.add_argument("--span", type=float, default=25.0)
    ap.add_argument("--stride", type=float, default=1.0)
    a = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(a.model)

    # (격자, 겹침비율, 입력크기, 원본도포함)
    modes = [
        ("현행 2x2+중앙 640", (2, 0.0, 640, True)),
        ("2x2 겹침0.2 640", (2, 0.2, 640, True)),
        ("3x3 겹침0.2 640", (3, 0.2, 640, True)),
        ("4x4 겹침0.2 640", (4, 0.2, 640, True)),
        ("3x3 겹침0.2 960", (3, 0.2, 960, True)),
        ("원본만 1280", (1, 0.0, 1280, False)),
        ("원본만 1920", (1, 0.0, 1920, False)),
    ]
    print(f"모델 {a.model}")
    print(f"정답시각 앞뒤 {a.span:.0f}초, {a.stride}초 간격\n")
    for stem in a.stems:
        print(f"===== {stem} =====", flush=True)
        print(f"  {'방식':22s} {'불최대':>7} {'연기최대':>8} {'불검출시각':>10}  {'GT':>5}")
        for name, mode in modes:
            bf, bs, at, g = scan(model, stem, mode, a.stride, a.span)
            mark = ""
            if at is not None and bf >= 0.2:
                # 이 시각이 채점 창 안으로 들어오는가 (알람 = 검출 + 10초)
                mark = "  ← 창 안" if g - 2 <= at + 10 <= g + 10 else "  (창 밖)"
            print(f"  {name:22s} {bf:7.3f} {bs:8.3f} {str(at):>10}  {g:5.0f}{mark}", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""침입 미검 영상에서 원거리 소형 인물이 타일 추론으로 잡히는지 시험.

배경(실측): 침입 실패 12편 중 여러 편이 '구역은 정확하고 사람도 구역 안에 있는데 검출 박스 0개'.
프레임을 그려 확인한 결과 사람이 원본 기준 30~70픽셀로 작다. 규칙이 아니라 검출이 문제.
여기서는 원본 한 장 추론과 격자 타일 추론을 같은 프레임에 돌려 검출 수·신뢰도를 비교한다.
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2

W = Path("/NHNHOME/WORKSPACE/26mss002_E3")
G = W / "vms"
VID = G / "data/원본데이터/kisa_배포_검증영상/deploy_val"   # 항목별 하위폴더에 mp4/xml 같이 있음
GTD = G / "data/원본데이터/kisa_배포_검증영상"


def gt_of(stem):
    for p in VID.rglob(f"{stem}.xml"):
        if p.exists():
            a = ET.parse(p).getroot().find(".//Alarm")
            h, m, s = a.findtext("StartTime").split(":")
            return int(h) * 3600 + int(m) * 60 + int(s)
    return None


def find_video(stem):
    for p in VID.rglob(f"{stem}.mp4"):
        return p
    for p in G.rglob(f"{stem}.mp4"):
        return p
    return None


def tiles_of(fr, grid, overlap):
    h, w = fr.shape[:2]
    if grid <= 1:
        return [(fr, 0, 0)]
    out = []
    th, tw = h // grid, w // grid
    oy, ox = int(th * overlap), int(tw * overlap)
    for gy in range(grid):
        for gx in range(grid):
            y0 = max(0, gy * th - oy); y1 = min(h, (gy + 1) * th + oy)
            x0 = max(0, gx * tw - ox); x1 = min(w, (gx + 1) * tw + ox)
            out.append((fr[y0:y1, x0:x1], x0, y0))
    return out


def detect(model, fr, grid, overlap, imgsz, conf):
    """반환: [(신뢰도, x1, y1, x2, y2)] 원본 좌표계"""
    res = []
    for crop, ox, oy in tiles_of(fr, grid, overlap):
        r = model.predict(crop, conf=conf, verbose=False, imgsz=imgsz, classes=[0])[0]
        for b in r.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            res.append((float(b.conf), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--stems", nargs="+",
                    default=["C00_005_0001", "C00_008_0002", "C00_070_0003",
                             "C00_126_0002", "C00_129_0002", "C00_275_0001"])
    ap.add_argument("--conf", type=float, default=0.15)
    ap.add_argument("--offsets", type=float, nargs="+", default=[0.0, 2.0, 5.0])
    a = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(a.model)

    modes = [("원본 640", (1, 0.0, 640)),
             ("원본 960", (1, 0.0, 960)),
             ("원본 1280", (1, 0.0, 1280)),
             ("2x2 겹침0.2 640", (2, 0.2, 640)),
             ("3x3 겹침0.2 640", (3, 0.2, 640)),
             ("3x3 겹침0.2 960", (3, 0.2, 960)),
             ("4x4 겹침0.2 640", (4, 0.2, 640))]
    print(f"모델 {a.model}  conf {a.conf}\n")
    for stem in a.stems:
        g = gt_of(stem); v = find_video(stem)
        if v is None or g is None:
            print(f"{stem}: 영상/GT 없음 (영상 {v}, GT {g})", flush=True)
            continue
        cap = cv2.VideoCapture(str(v)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        print(f"===== {stem}  GT {g}s =====", flush=True)
        print(f"  {'방식':20s} " + " ".join(f"GT{o:+.0f}s:검출/최고conf".rjust(20) for o in a.offsets), flush=True)
        for name, (grid, ov, imgsz) in modes:
            cells = []
            for off in a.offsets:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(max(0, g + off) * fps))
                ok, fr = cap.read()
                if not ok:
                    cells.append("     -"); continue
                d = detect(model, fr, grid, ov, imgsz, a.conf)
                mx = max((x[0] for x in d), default=0.0)
                cells.append(f"{len(d):d}개/{mx:.2f}".rjust(20))
            print(f"  {name:20s} " + " ".join(cells), flush=True)
        cap.release()
        print(flush=True)


if __name__ == "__main__":
    main()

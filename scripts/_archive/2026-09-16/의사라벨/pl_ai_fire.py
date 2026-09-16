# -*- coding: utf-8 -*-
"""AI산불 정지영상(라벨 없음)에 base+타일 의사라벨 생성 + 표본 추출.

fire_v2 교훈 반영: 통주입이 아니라 라벨 품질 필터 + 표본 상한으로 소량 정밀 주입.
- base+타일 conf 0.35 이상 박스만 라벨
- 0.15~0.35 만 있는 애매 프레임은 버림
- 폴더별(Blender/CycleGAN) 상한으로 균형
"""
import argparse
import random
from pathlib import Path

import cv2
from ultralytics import YOLO


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="AI산불 정지영상 루트 (재귀)")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-folder", type=int, default=1500, help="하위 폴더별 라벨 상한")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    random.seed(a.seed)
    out = Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    model = YOLO(a.model)

    root = Path(a.images)
    folders = sorted({p.parent for p in root.rglob("*.png")})
    total = skip = 0
    for folder in folders:
        pngs = sorted(folder.glob("*.png"))
        random.shuffle(pngs)
        made = 0
        for png in pngs:
            if made >= a.per_folder:
                break
            img = cv2.imread(str(png))
            if img is None:
                continue
            dets = nms(infer_tiled(model, img, 0.15))
            strong = [d for d in dets if d[1] >= 0.35]
            if not strong:
                skip += 1
                continue
            h, w = img.shape[:2]
            stem = f"ai_{folder.name[:12]}_{png.stem}"[:80]
            cv2.imwrite(str(out / "images" / (stem + ".jpg")), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            (out / "labels" / (stem + ".txt")).write_text("\n".join(
                f"{c} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}"
                for c, _, x1, y1, x2, y2 in strong))
            made += 1
        total += made
        print(f"{folder.name}: 라벨 {made} (스킵 누적 {skip})", flush=True)
    print(f"합계 {total}장")


if __name__ == "__main__":
    main()

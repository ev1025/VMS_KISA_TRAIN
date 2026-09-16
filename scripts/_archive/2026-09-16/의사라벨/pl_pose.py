# -*- coding: utf-8 -*-
"""person_pl 이미지에 x-pose 교사로 키포인트 의사라벨 생성 (YOLO pose 형식, kpt 17×3)."""
import argparse
import os
import shutil
from pathlib import Path

import cv2
from ultralytics import YOLO


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="person_pl 루트 (images/labels × train/val)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--teacher", default="yolo11x-pose.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    a = ap.parse_args()

    model = YOLO(a.teacher)
    src = Path(a.src)
    out = Path(a.out)
    for split in ("train", "val"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        imgs = sorted((src / "images" / split).glob("*.jpg"))
        n_pos = n_bg = 0
        for i, img_path in enumerate(imgs, 1):
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            h, w = img.shape[:2]
            r = model.predict(img, conf=a.conf, imgsz=640, verbose=False)[0]
            lines = []
            if r.keypoints is not None and len(r.boxes):
                kdata = r.keypoints.data.cpu().numpy()   # (n,17,3)
                for b, kp in zip(r.boxes, kdata):
                    x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                    row = [f"0 {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}"]
                    for kx, ky, kc in kp:
                        v = 2 if kc > 0.5 else (1 if kc > 0.2 else 0)
                        row.append(f"{kx/w:.6f} {ky/h:.6f} {v}")
                    lines.append(" ".join(row))
            link_or_copy(img_path, out / "images" / split / img_path.name)
            (out / "labels" / split / (img_path.stem + ".txt")).write_text("\n".join(lines))
            if lines:
                n_pos += 1
            else:
                n_bg += 1
            if i % 2000 == 0:
                print(f"  {split} {i}/{len(imgs)}", flush=True)
        print(f"{split}: 포즈 {n_pos} · 빈 라벨 {n_bg}", flush=True)
    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\n"
        f"kpt_shape: [17, 3]\nflip_idx: [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]\n"
        f"nc: 1\nnames: ['person']\n")
    print("완료")


if __name__ == "__main__":
    main()

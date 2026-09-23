# -*- coding: utf-8 -*-
"""합성한 눈 배경 방화 데이터를 지금 모델로 검증해 '인식 안 되는 것'을 가른다.

왜 (2026-09-23 사용자 지시)
    합성을 만들어 놓고 그게 쓸모 있는지 보려면, 지금 모델이 이미 잘 잡는지부터 봐야 한다.
        이미 잘 잡는 그림    학습에 넣어도 새로 배울 것이 없다
        못 잡는 그림        여기가 배울 거리다. 따로 모아 눈으로 확인한다
    검증에는 정직한 기준선 f960_mask_hn_x2_fog3_20260920 best.pt 를 쓴다.
    채점과 같은 방식(타일 6장)으로 본다. 다르게 보면 그 숫자로 판단할 수 없다.

무엇을 남기나
    <출력>/<세트이름>/            합성 이미지 전부(라벨 txt 같이)
    <출력>/<세트이름>/_인식안됨/   그 세트에서 못 잡은 것만 따로(견본)
    <출력>/<세트이름>/결과.txt     세트별 인식률

사용
    python scripts/check_snow_sets.py <가중치.pt> --sets a,b,c --out <폴더> [--conf 0.14] [--max 0]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
IMGSZ = 960
CONF = 0.14              # 후보 규칙 A 의 불 임계. 채점에서 쓰려는 값으로 본다


def 타일예측(model, im):
    """채점 경로와 같게 전체 1장 + 사분면 4장 + 가운데 1장을 본다. 불(cls 0) 박스만 돌려준다."""
    h, w = im.shape[:2]
    crops = [(im, 0, 0)]
    for x, y in ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4)):
        crops.append((im[y:y + h // 2, x:x + w // 2], x, y))
    out = []
    for c, ox, oy in crops:
        r = model.predict(c, conf=0.05, verbose=False, imgsz=IMGSZ)[0]
        for b in r.boxes:
            if int(b.cls) != 0:
                continue
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
            out.append((x1 + ox, y1 + oy, x2 + ox, y2 + oy, float(b.conf)))
    return out


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    it = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - it
    return it / u if u > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--sets", required=True, help="쉼표로 구분한 학습셋 이름")
    ap.add_argument("--out", required=True, help="결과를 담을 폴더")
    ap.add_argument("--conf", type=float, default=CONF)
    ap.add_argument("--max", type=int, default=0, help="세트당 검사할 장수(0=전부)")
    a = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(a.model)
    out_root = Path(a.out)
    out_root.mkdir(parents=True, exist_ok=True)
    요약 = []

    for name in a.sets.split(","):
        name = name.strip()
        d = V / "data/학습데이터" / name
        if not d.is_dir():
            print("없음: %s" % name)
            continue
        dst = out_root / name
        (dst / "_인식안됨").mkdir(parents=True, exist_ok=True)

        labs = sorted((d / "labels/train").glob("*.txt"))
        if a.max:
            labs = labs[:a.max]
        양성 = 잡음 = 놓침 = 음성 = 헛울림 = 0
        for i, t in enumerate(labs, 1):
            img = d / "images/train" / (t.stem + ".jpg")
            if not img.is_file():
                continue
            gt = [r.split() for r in t.read_text().split("\n") if r.strip()]
            gt = [r for r in gt if int(r[0]) == 0]
            im = cv2.imread(str(img))
            if im is None:
                continue
            H, W = im.shape[:2]
            preds = [p for p in 타일예측(model, im) if p[4] >= a.conf]

            # 합성 이미지와 라벨은 통째로 옮긴다(사용자가 눈으로 보려고 한다)
            shutil.copy2(img, dst / img.name)
            shutil.copy2(t, dst / t.name)

            if not gt:
                음성 += 1
                if preds:
                    헛울림 += 1
                continue
            양성 += 1
            맞음 = False
            for g in gt:
                cx, cy, w, h = [float(v) for v in g[1:5]]
                box = ((cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H)
                if any(iou(box, p) >= 0.1 for p in preds):
                    맞음 = True
                    break
            if 맞음:
                잡음 += 1
            else:
                놓침 += 1
                vis = im.copy()
                for g in gt:
                    cx, cy, w, h = [float(v) for v in g[1:5]]
                    cv2.rectangle(vis, (int((cx - w / 2) * W), int((cy - h / 2) * H)),
                                  (int((cx + w / 2) * W), int((cy + h / 2) * H)), (0, 255, 0), 2)
                cv2.imwrite(str(dst / "_인식안됨" / img.name), vis)
            if i % 300 == 0:
                print("  %s %d/%d" % (name, i, len(labs)), flush=True)

        율 = 100.0 * 잡음 / max(1, 양성)
        줄 = ("%s\n  불 있는 그림 %d장 중 잡음 %d · 못 잡음 %d  (인식률 %.1f%%)\n"
              "  불 없는 그림 %d장 중 헛울림 %d\n  임계 %.2f · 타일 6장 · imgsz %d\n"
              % (name, 양성, 잡음, 놓침, 율, 음성, 헛울림, a.conf, IMGSZ))
        print(줄, flush=True)
        (dst / "결과.txt").write_text(줄, encoding="utf-8")
        요약.append((name, 양성, 잡음, 놓침, 율, 음성, 헛울림))

    print("=== 요약 ===")
    print("%-28s %7s %7s %7s %8s %9s" % ("세트", "양성", "잡음", "못잡음", "인식률", "헛울림"))
    묶음 = []
    for n, p, c, m, r, ng, fp in 요약:
        줄 = "%-28s %7d %7d %7d %7.1f%% %9d" % (n, p, c, m, r, fp)
        print(줄)
        묶음.append(줄)
    (out_root / "요약.txt").write_text(
        "합성 눈 배경 방화 데이터 검증 (모델 %s · 임계 %.2f)\n\n" % (Path(a.model).parts[-4], a.conf)
        + "%-28s %7s %7s %7s %8s %9s\n" % ("세트", "양성", "잡음", "못잡음", "인식률", "헛울림")
        + "\n".join(묶음) + "\n\n"
        + "인식률이 낮을수록 모델이 아직 모르는 그림이다. 학습에 넣을 값어치가 크다.\n"
          "각 세트의 _인식안됨/ 에 못 잡은 그림만 초록 네모(정답)와 함께 들어 있다.\n",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

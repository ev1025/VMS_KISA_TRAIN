# -*- coding: utf-8 -*-
"""FASDD 에서 설경·안개 장면만 뽑아 방화 학습용 보강셋을 만든다.

왜: 배포 10편 중 못 잡는 2편이 설경(눈밭 위 작은 불꽃)과 짙은 안개인데,
    우리 학습 풀에서 이 조건이 있는 곳은 FASDD 뿐이다(연구개발 75편은 전부 열대 야외, 24k 는 실내·주택 화재).
    FASDD 는 박스 라벨이 이미 있으므로 손라벨 없이 바로 쓸 수 있다.
판별: 화면의 상당 부분이 '밝고 채도 낮은' 화소인 이미지.
     설경 = 그 영역이 화면 아래쪽(지면)에 몰려 있고 위아래 밝기 차가 작음
     안개 = 화면 전체 명암 대비가 낮음
FASDD 클래스는 0=fire, 1=smoke 로 우리와 같은 순서인지 data.yaml 로 확인 후 사용.
"""
import argparse
import glob
import json
import os
import random
from pathlib import Path

import cv2
import numpy as np

G = Path(__file__).resolve().parents[1]
SRC = G / "data/학습데이터/fasdd_yolo"


def kind_of(path):
    """(분류, 지표들). 분류: 설경 / 안개 / None"""
    im = cv2.imread(path, cv2.IMREAD_REDUCED_COLOR_4)
    if im is None:
        return None, None
    h, w = im.shape[:2]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2].astype(np.float32)
    s = hsv[:, :, 1].astype(np.float32)
    white = (v > 185) & (s < 55)
    wr = float(white.mean())
    if wr < 0.18:
        return None, None
    lower = float(white[h // 2:].mean())        # 아래 절반의 흰 비율
    upper = float(white[:h // 2].mean())        # 위 절반(하늘·연기)
    contrast = float(v.std())
    info = dict(white=round(wr, 3), lower=round(lower, 3), upper=round(upper, 3), contrast=round(contrast, 1))
    # 설경: 지면(아래)이 하늘(위)보다 더 하얗다 = 눈 덮인 땅
    if lower > upper + 0.12 and lower > 0.3:
        return "설경", info
    # 안개: 전체적으로 대비가 낮고 위아래가 고르게 뿌옇다
    if contrast < 32 and wr > 0.35 and abs(lower - upper) < 0.2:
        return "안개", info
    return None, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(G / "data/학습데이터/fasdd_snowfog"))
    ap.add_argument("--limit", type=int, default=0, help="스캔할 최대 장수(0=전부)")
    ap.add_argument("--need-fire", action="store_true", help="불 박스가 있는 것만")
    a = ap.parse_args()

    print("FASDD data.yaml:", (SRC / "data.yaml").read_text().strip().replace("\n", " | "), flush=True)
    imgs = sorted(glob.glob(str(SRC / "images/train/*")))
    if a.limit:
        random.Random(0).shuffle(imgs); imgs = imgs[:a.limit]
    print(f"스캔 {len(imgs)}장", flush=True)

    out = Path(a.out)
    for d in ("images/train", "labels/train"):
        (out / d).mkdir(parents=True, exist_ok=True)
    picked = {"설경": [], "안개": []}
    for i, p in enumerate(imgs, 1):
        k, info = kind_of(p)
        if k is None:
            continue
        lb = SRC / "labels/train" / (Path(p).stem + ".txt")
        if not lb.exists():
            continue
        txt = lb.read_text().strip()
        cls = {ln.split()[0] for ln in txt.splitlines() if ln.strip()}
        if a.need_fire and "0" not in cls:
            continue
        picked[k].append((p, str(lb), sorted(cls), info))
        if i % 10000 == 0:
            print(f"  {i}/{len(imgs)} · 설경 {len(picked['설경'])} 안개 {len(picked['안개'])}", flush=True)

    meta = {}
    for k, rows in picked.items():
        for p, lb, cls, info in rows:
            stem = Path(p).stem
            name = f"{'SNOW' if k == '설경' else 'FOG'}_{stem}"
            ext = Path(p).suffix
            os.symlink(p, out / "images/train" / (name + ext)) if not (out / "images/train" / (name + ext)).exists() else None
            os.symlink(lb, out / "labels/train" / (name + ".txt")) if not (out / "labels/train" / (name + ".txt")).exists() else None
            meta[name] = dict(kind=k, cls=cls, **info)
    json.dump(meta, open(out / "meta.json", "w", encoding="utf-8"), ensure_ascii=False)

    nfire = sum(1 for v in meta.values() if "0" in v["cls"])
    nsmoke = sum(1 for v in meta.values() if "1" in v["cls"])
    print(f"\n설경 {len(picked['설경'])}장 · 안개 {len(picked['안개'])}장 (합 {len(meta)})")
    print(f"  불 박스 있는 것 {nfire} · 연기 박스 있는 것 {nsmoke}")
    print(f"저장 → {out}")


if __name__ == "__main__":
    main()

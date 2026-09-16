# -*- coding: utf-8 -*-
"""사람 학습셋에 눈·비를 합성한다.

[상태] 지금 실패하는 편의 처방이 아니다. 학습에 쓰지 않는다 (2026-09-16 측정).

만든 이유 (당시 가설)
    배포 검증영상에서 침입·배회 모두 실패가 악천후 편에만 몰려 있었다.
        침입  악천후 없음 19/19(100%)   악천후 8/11(73%)
        배회  악천후 없음 15/15(100%)   악천후 12/15(80%)
    연구개발 825편에는 눈·비가 한 편도 없으니 합성으로 채우자는 생각이었다.

왜 안 쓰나 (측정한 것)
    1. 이 합성이 만드는 열화와 실제로 실패하는 열화가 다르다.
       잘 잡는 편 60프레임에 씌워 보면 평균 0.856 -> 눈 0.701 · 비 0.831 로 대체로 버틴다.
       크게 무너지는 것은 야간 편 한둘뿐인데(예: C00_120_0001 -0.70), 이는 아래쪽을 240 까지
       밝히는 눈쌓임 흉내가 야간 화면을 통째로 날리기 때문이지 진짜 눈의 모습이 아니다.
    2. 정작 진짜 눈이 내리는 편은 이미 잘 잡는다.
       C00_211_0002(강설 주간)에서 사람 신뢰도 0.79~0.89. 눈 자체는 문제가 아니었다.
    3. 실패 5편은 '날씨로 대비가 낮아져서' 가 아니라 구역 안에서 아예 안 잡힌다.
       GT 앞뒤 창에서 구역 안 검출 표본 수 (제출 경로 그대로 · 구역 제한)
           침입 C00_249_0003  0/71      침입 C00_255_0001  0/71
           침입 C00_275_0001  0/71      배회 C00_225_0001  0/71
           배회 C00_115_0001  3/71 (체류 6초를 못 채운다)
           대조 침입 C00_005_0001 15/71 연속 · 배회 C00_001_0001 59/71 연속
       원인은 소형·가림·저대비다(담장 난간 뒤 상반신, 우산으로 가린 상체, 야간 적외선).
       합성은 이 중 어느 것도 만들지 않는다.

    그래서 처방은 합성이 아니라 그 조건의 손라벨이다. 자세한 내용은 docs/EXPERIMENTS.md 참고.
    (파일은 남겨 둔다. 나중에 '악천후 일반화' 를 따로 재고 싶을 때 쓸 수 있다.)

무엇을 하나
    기존 학습 이미지에 눈 또는 비를 덧씌운 사본을 만든다. 라벨(사람 박스)은 그대로 쓴다.
    날씨는 사람 위치를 바꾸지 않으므로 좌표가 유효하다.

    눈  : 흰 점을 크기·밝기를 섞어 뿌리고 약한 뿌옇게. 쌓인 눈을 흉내내려 아래쪽을 더 밝게 한다.
    비  : 기울어진 가는 선을 그리고 대비를 낮춘다. 젖은 바닥의 반사를 위해 아래쪽 대비를 더 낮춘다.

    07_augment_domains.py 의 augment_fog 와 같은 방식(저주파 얼룩 + 알파 합성)을 따른다.

사용
    python scripts/weather_aug.py <원본셋> --out <새셋> --ratio 0.3
    python scripts/weather_aug.py <원본셋> --preview 6     # 6장만 만들어 눈으로 확인
"""
import argparse
import os
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

IMG_EXT = {".jpg", ".jpeg", ".png"}


def snow(img):
    """눈. 흰 점 + 약한 뿌옇게 + 아래쪽 반사."""
    h, w = img.shape[:2]
    out = img.astype(np.float32)

    # 저주파 뿌옇게 (눈발 사이 산란)
    patch = cv2.resize(np.random.rand(h // 64 + 1, w // 64 + 1).astype(np.float32), (w, h))
    haze = np.clip(random.uniform(0.10, 0.28) + (patch - 0.5) * 0.12, 0.05, 0.4)[..., None]
    out = out * (1 - haze) + random.uniform(200, 235) * haze

    # 눈송이. 가까운 것은 크고 흐리게, 먼 것은 작고 또렷하게
    for size, n, blur in ((1, int(w * h / 900), 0), (2, int(w * h / 4000), 3), (4, int(w * h / 20000), 7)):
        layer = np.zeros((h, w), np.float32)
        xs = np.random.randint(0, w, n)
        ys = np.random.randint(0, h, n)
        for x, y in zip(xs, ys):
            cv2.circle(layer, (int(x), int(y)), size, random.uniform(0.6, 1.0), -1)
        if blur:
            layer = cv2.GaussianBlur(layer, (blur * 2 + 1,) * 2, 0)
        out = out * (1 - layer[..., None]) + 245 * layer[..., None]

    # 쌓인 눈: 아래쪽을 밝게
    grad = np.linspace(0, random.uniform(0.10, 0.25), h).astype(np.float32)[:, None, None]
    out = out * (1 - grad) + 240 * grad
    return np.clip(out, 0, 255).astype(np.uint8)


def rain(img):
    """비. 기울어진 빗줄기 + 대비 저하 + 젖은 바닥."""
    h, w = img.shape[:2]
    out = img.astype(np.float32)

    # 전체 대비를 낮춘다(비 오는 날은 흐리다)
    out = out * random.uniform(0.72, 0.88) + random.uniform(18, 38)

    # 빗줄기
    layer = np.zeros((h, w), np.float32)
    slant = random.uniform(-0.45, 0.45)
    length = random.randint(12, 30)
    for _ in range(int(w * h / 2500)):
        x, y = random.randrange(w), random.randrange(h)
        x2, y2 = int(x + slant * length), y + length
        cv2.line(layer, (x, y), (x2, y2), random.uniform(0.25, 0.55), 1)
    layer = cv2.GaussianBlur(layer, (3, 3), 0)
    out = out * (1 - layer[..., None]) + 200 * layer[..., None]

    # 젖은 바닥: 아래쪽 대비를 더 낮춘다
    grad = np.linspace(0, random.uniform(0.08, 0.20), h).astype(np.float32)[:, None, None]
    out = out * (1 - grad) + 150 * grad
    return np.clip(out, 0, 255).astype(np.uint8)


KINDS = {"snow": snow, "rain": rain}


def label_of(img_path):
    """images/ 옆의 labels/ 경로. 윈도 역슬래시는 슬래시로 맞춰 본다."""
    q = str(img_path).replace("\\", "/")
    if "/images/" not in q:
        return None
    return Path(q.replace("/images/", "/labels/")).with_suffix(".txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", help="원본 셋 루트(images/ labels/ 를 담은 곳)")
    ap.add_argument("--out", help="새 셋 루트(증강 사본만 담는다)")
    ap.add_argument("--ratio", type=float, default=0.3, help="원본 대비 만들 비율")
    ap.add_argument("--preview", type=int, default=0, help="이 장수만 만들어 눈으로 확인(--out 없이)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    random.seed(a.seed); np.random.seed(a.seed)

    src = Path(a.dataset)
    imgs = [p for p in src.rglob("*") if p.suffix.lower() in IMG_EXT and "/labels/" not in str(p)]
    if not imgs:
        print(f"이미지가 없다: {src}"); return 2
    print(f"원본 {len(imgs):,}장")

    if a.preview:
        out = Path("dumps/weather_preview"); out.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(random.sample(imgs, min(a.preview, len(imgs)))):
            im = cv2.imread(str(p))
            if im is None:
                continue
            kind = list(KINDS)[i % len(KINDS)]
            cv2.imwrite(str(out / f"{i}_원본_{p.stem}.jpg"), im)
            cv2.imwrite(str(out / f"{i}_{kind}_{p.stem}.jpg"), KINDS[kind](im))
        print(f"미리보기 {out.resolve()} 에 만들었다. 눈으로 확인한 뒤 --out 으로 본 생성을 한다.")
        return 0

    if not a.out:
        print("--out 또는 --preview 가 필요하다"); return 2
    dst = Path(a.out)
    n = int(len(imgs) * a.ratio)
    pick = random.sample(imgs, min(n, len(imgs)))
    made = 0
    for p in pick:
        kind = random.choice(list(KINDS))
        im = cv2.imread(str(p))
        if im is None:
            continue
        rel = p.relative_to(src)
        o = dst / rel.parent / f"{p.stem}_{kind}{p.suffix}"
        o.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(o), KINDS[kind](im))
        lb = label_of(p)
        if lb and lb.exists():                     # 날씨는 사람 위치를 안 바꾼다. 라벨 그대로.
            ol = label_of(o)
            ol.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(lb, ol)
        made += 1
        if made % 500 == 0:
            print(f"  {made}/{len(pick)}", flush=True)
    print(f"완료 {made:,}장 -> {dst.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

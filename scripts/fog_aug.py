# -*- coding: utf-8 -*-
"""손라벨 방화 CCTV 프레임에 대기 산란 안개를 씌워 학습셋을 만든다. 라벨은 그대로 복사한다(박스 위치 불변).

왜 (2026-09-19)
    방화 미검 3편이 전부 눈·안개인데 학습 원본(연구개발 75편)에는 눈·안개가 0편이다.
    안개 양성은 FASDD 에 18장뿐이라 데이터로는 못 채운다. 같은 카메라 계열(연구개발 CCTV)의 맑은 손라벨 프레임에
    실제 안개의 물리량을 씌우는 것이 도메인(카메라)과 조건(안개)을 동시에 맞추는 유일한 길이다.

물리량은 어디서 (scripts/fog_stats.py, 2026-09-19 실측 · Dark Channel Prior)
    실제 안개+불(FASDD 18장):  투과율 t 0.20~0.48(중앙 0.30) · 대기광 A 0.85~1.00 · 채도 0.10 · 대비 0.095
    맑은 CCTV 손라벨 프레임:    t 0.61~0.79(중앙 0.69)         · 채도 0.17 · 대비 0.20
    채점 195(비교만, 학습·튜닝에 안 씀): t 0.29 · A 0.62 · 채도 0.04 · 대비 0.055  -> FASDD 안개 분포 안에 있다
    → 합성은 FASDD 실제 안개 분포에서 뽑는다: 목표 t 를 맑은 값의 0.35~0.70 배로 낮추고(중앙 0.30~0.48),
      A 는 0.60~1.00 의 무채색, 채도는 0.3~0.6 배, 대비는 따라서 낮아진다.

모델  I = J·t(x) + A·(1 - t(x)),  t(x) = t0 · exp(-β · d(y)),  d(y) = 세로 위치(위가 멀다, 0~1)
      CCTV 는 지면을 내려보는 카메라라 화면 위쪽이 먼 곳이다(fog_stats 에서 실제 안개 t위 0.48 < 아래 0.92).
      깊이 추정 모델 없이도 이 한 축이 실제 안개의 위·아래 차이를 재현한다.

산출  data/학습데이터/<이름>/{images,labels}/train · train.txt · data.yaml · meta.json (원본·파라미터 기록)
      양성 프레임은 옅은/중간/짙은 3벌, 배경(하드네거) 프레임은 1벌(하드네거 비율을 원본과 비슷하게 둔다).

사용
    python scripts/fog_aug.py --src handset_fire_hn_20260917 --name fire_mask_hn_fog_20260919
    python scripts/fog_aug.py --probe /tmp/fog_probe --n 60      # 검증용: 맑은/옅은/짙은 3벌 표본만 만든다
"""
import argparse
import json
import random
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
TD = V / "data/학습데이터"

# 같은 잣대(DCP)로 다시 잰 값(2026-09-19 표본 80장): light t 0.30 · heavy t 0.24 (실제 안개+불 중앙 0.30 · 채점 195 0.29).
# 실제 안개 분포의 옅은 쪽(t 0.40~0.48)이 비어서 mild 를 더 두고, heavy 의 A 는 195 처럼 어두운 회색(0.5)까지 내린다.
LEVELS = {"mild": dict(t=(0.72, 0.90), A=(0.80, 1.00), sat=(0.55, 0.75)),      # 옅은 안개: 잰 t 0.40 근처
          "light": dict(t=(0.55, 0.72), A=(0.75, 1.00), sat=(0.45, 0.65)),     # 중간 안개: 잰 t 0.30 (실제 중앙)
          "heavy": dict(t=(0.35, 0.52), A=(0.50, 0.95), sat=(0.25, 0.45))}     # 짙은 안개: 잰 t 0.24 (195 대비 0.055 수준)


def fog(img, level, rnd):
    """맑은 BGR 프레임에 안개를 씌운다. 파라미터는 LEVELS 범위에서 뽑아 기록용으로 함께 돌려준다."""
    p = LEVELS[level]
    t0 = rnd.uniform(*p["t"])                     # 화면 아래(가까운 곳)의 투과율
    beta = rnd.uniform(0.6, 1.4)                  # 위로 갈수록 t 가 exp(-beta) 배까지 준다
    A = rnd.uniform(*p["A"])
    # 야간 프레임에 흰 대기광을 섞으면 새벽처럼 밝아진다(견본 확인 2026-09-19). 대기광은 그 장면 밝기에 매여야 한다:
    # 어두운 장면의 안개는 어두운 회색이다. 상한 = 0.35 + 1.2 x 평균밝기 (주간 0.45 -> 0.89 · 야간 0.15 -> 0.53)
    mean_gray = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()) / 255.0
    A = min(A, 0.35 + 1.2 * mean_gray)
    A_rgb = np.clip(np.array([A + rnd.uniform(-0.03, 0.03) for _ in range(3)], dtype=np.float32), 0, 1)
    sat = rnd.uniform(*p["sat"])
    f = img.astype(np.float32) / 255.0
    h, w = f.shape[:2]
    d = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None]          # 위 1(멀다) → 아래 0
    t = (t0 * np.exp(-beta * d)).astype(np.float32)                    # h x 1
    t = np.repeat(t, w, axis=1)[..., None]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] *= sat                                                  # 채도부터 낮춘다(안개는 색을 지운다)
    j = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255.0
    if rnd.random() < 0.7:
        j = cv2.GaussianBlur(j, (0, 0), rnd.uniform(0.4, 1.0))         # 윤곽이 조금 흐려진다
    out = j * t + A_rgb[None, None, :] * (1.0 - t)
    return (np.clip(out, 0, 1) * 255).astype(np.uint8), dict(level=level, t0=round(t0, 3), beta=round(beta, 2), A=round(A, 3), sat=round(sat, 2))


def label_of(img_path):
    lp = Path(str(img_path).replace("/images/", "/labels/")).with_suffix(".txt")
    return lp if lp.is_file() else None


def build(src, name, rnd):
    lines = [l.strip() for l in open(TD / src / "train.txt", encoding="utf-8") if l.strip()]
    out = TD / name
    (out / "images/train").mkdir(parents=True, exist_ok=True)
    (out / "labels/train").mkdir(parents=True, exist_ok=True)
    made, log, t0 = [], {}, time.time()
    n_pos = n_neg = 0
    for i, src_img in enumerate(lines):
        img = cv2.imread(src_img)
        lp = label_of(src_img)
        if img is None or lp is None:
            continue
        positive = bool(lp.read_text(encoding="utf-8").strip())
        levels = ["mild", "light", "heavy"] if positive else [rnd.choice(["mild", "light", "heavy"])]
        n_pos += positive; n_neg += not positive
        for lv in levels:
            fogged, prm = fog(img, lv, rnd)
            stem = Path(src_img).stem + "_fog" + lv[0]
            dst = out / "images/train" / (stem + ".jpg")
            cv2.imwrite(str(dst), fogged, [cv2.IMWRITE_JPEG_QUALITY, 92])
            shutil.copyfile(lp, out / "labels/train" / (stem + ".txt"))
            made.append(str(dst)); log[stem] = dict(src=src_img, **prm)
        if (i + 1) % 500 == 0:
            print("  %d/%d  (%.0f초)" % (i + 1, len(lines), time.time() - t0), flush=True)
    (out / "train.txt").write_text("\n".join(made) + "\n", encoding="utf-8")
    (out / "data.yaml").write_text("path: %s\ntrain: %s\nval: %s\nnc: 2\nnames: ['fire', 'smoke']\n"
                                   % (out, out / "train.txt", out / "train.txt"), encoding="utf-8")
    meta = dict(name=name, mode="fire", built=time.strftime("%Y-%m-%d %H:%M:%S"), source=src,
                what="손라벨 방화 프레임에 대기 산란 안개 합성. 라벨은 원본 그대로",
                levels=LEVELS, n_source=len(lines), n_source_pos=n_pos, n_source_neg=n_neg, n_out=len(made),
                params_of_each="params.json", physics="I = J*t + A*(1-t), t = t0*exp(-beta*d), d=세로(위=멀다)",
                measured_from="scripts/fog_stats.py 2026-09-19 (FASDD 실제 안개+불 18장 분포. 채점 편은 비교만)")
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "params.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
    print("완료 %s: 원본 %d(양성 %d·배경 %d) → %d장 (%.0f초)" % (name, len(lines), n_pos, n_neg, len(made), time.time() - t0))


def probe(src, out_dir, n, rnd):
    """검증용 표본: 양성 프레임 n 장을 골라 맑은/옅은/짙은 3벌을 나란히 저장한다."""
    lines = [l.strip() for l in open(TD / src / "train.txt", encoding="utf-8") if l.strip()]
    pos = [l for l in lines if (label_of(l) and label_of(l).read_text(encoding="utf-8").strip())]
    out = Path(out_dir); (out / "clear").mkdir(parents=True, exist_ok=True)
    for lv in LEVELS:
        (out / lv).mkdir(exist_ok=True)
    for src_img in rnd.sample(pos, min(n, len(pos))):
        img = cv2.imread(src_img); stem = Path(src_img).stem
        cv2.imwrite(str(out / "clear" / (stem + ".jpg")), img)
        for lv in LEVELS:
            cv2.imwrite(str(out / lv / (stem + ".jpg")), fog(img, lv, rnd)[0])
        shutil.copyfile(label_of(src_img), out / (stem + ".txt"))
    print("검증 표본 %d장 x 3벌 → %s" % (min(n, len(pos)), out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="handset_fire_hn_20260917")
    ap.add_argument("--name", default="fire_mask_hn_fog_20260919")
    ap.add_argument("--probe", default=None, help="검증 표본만 만들 폴더")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    if a.probe:
        probe(a.src, a.probe, a.n, rnd)
    else:
        build(a.src, a.name, rnd)


if __name__ == "__main__":
    sys.exit(main())

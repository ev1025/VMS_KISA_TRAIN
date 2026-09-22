# -*- coding: utf-8 -*-
"""안개 합성 파라미터를 실제 안개 영상에서 잰다. 읽기만 한다(GPU 없음).

왜 (2026-09-19)
    방화 미검 편 195(주간 안개)를 채우려면 안개 합성이 필요한데, 흰 필터를 덮는 식이면 모델이 배우는 열화와
    실제 열화가 달라진다(09-16 사람 눈 합성이 그렇게 폐기됐다). 대기 산란 모델 I = J·t + A·(1-t) 의
    A(대기광)와 t(투과율)를 실제 안개 영상에서 재고, 그 분포 안에서 합성한다.

어떻게 재나 (Dark Channel Prior, He 2009)
    dark = 채널 최소값의 15x15 최소 필터.  A = dark 상위 0.1% 위치의 원본 픽셀 평균.  t = 1 - 0.95 · dark / A
    안개가 짙을수록 dark 가 밝아져 t 가 0 에 가까워진다. 맑은 영상은 t 가 1 근처.

무엇을 재나 (묶음별)
    실제 안개 (파라미터 출처)   wildfire_fog_neg 표본 · FASDD 안개 양성 18장     -> 합성에 쓸 A·t 분포
    맑은 CCTV (합성 입력)      손라벨 방화 프레임 표본                            -> 원본 상태
    채점 편 (비교만)           195(안개) · 012(맑음) 프레임 몇 장                -> 합성이 195 근처로 가는지 확인. 학습·튜닝에 안 쓴다

사용
    python scripts/fog_stats.py
"""
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import kisa_paths as KP   # noqa: E402

TD = V / "data/학습데이터"


def dcp(img, patch=15, omega=0.95):
    """대기광 A(0~1, 채널 평균)와 픽셀 투과율 지도 t 를 돌려준다. img 는 BGR uint8."""
    f = img.astype(np.float32) / 255.0
    dark = cv2.erode(f.min(axis=2), np.ones((patch, patch), np.uint8))
    n = max(1, int(dark.size * 0.001))
    idx = np.argpartition(dark.ravel(), -n)[-n:]
    A = f.reshape(-1, 3)[idx].mean(axis=0)
    t = 1.0 - omega * dark / max(1e-3, float(A.max()))
    return float(A.mean()), np.clip(t, 0.05, 1.0)


def stats(img):
    if img is None:
        return None
    h, w = img.shape[:2]
    if w > 960:
        img = cv2.resize(img, (960, int(h * 960 / w)))
    A, t = dcp(img)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H = t.shape[0]
    return dict(A=A, t=float(t.mean()), t_top=float(t[: H // 3].mean()), t_bot=float(t[-H // 3:].mean()),
                bright=float(g.mean() / 255), contrast=float(g.std() / 255), sat=float(hsv[..., 1].mean() / 255))


def summarize(name, rows):
    rows = [r for r in rows if r]
    if not rows:
        print("  %-26s 표본 없음" % name); return
    def q(k):
        v = sorted(r[k] for r in rows)
        return v[len(v) // 10], v[len(v) // 2], v[9 * len(v) // 10]
    print("  %-26s %3d장 | A %.2f/%.2f/%.2f | t %.2f/%.2f/%.2f | t위 %.2f 아래 %.2f | 밝기 %.2f | 대비 %.3f | 채도 %.2f"
          % ((name, len(rows)) + q("A") + q("t") + (q("t_top")[1], q("t_bot")[1], q("bright")[1], q("contrast")[1], q("sat")[1])))


def frames(stem, times):
    mp4 = KP.find_mp4(stem)
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    out = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps)); ok, fr = cap.read()
        if ok:
            out.append(fr)
    return out


def main():
    rnd = random.Random(0)
    print("묶음                        장수 | A 10/50/90%            | t 10/50/90%            | t 위·아래 1/3 | 밝기 | 대비 | 채도")
    fog_neg = [str(x) for x in (TD / "wildfire_fog_neg/images").rglob("*") if x.suffix.lower() in (".jpg", ".jpeg", ".png")]
    summarize("실제 안개 배경(wildfire_fog_neg)", [stats(cv2.imread(p)) for p in rnd.sample(fog_neg, 150)])
    meta = json.load(open(TD / "fasdd_snowfog/meta.json", encoding="utf-8"))
    fog_pos = [k for k, v in meta.items() if v.get("kind") == "안개" and v.get("cls")]
    imgs = list((TD / "fasdd_snowfog/images").rglob("*"))
    byname = {p.stem: p for p in imgs if p.suffix.lower() in (".jpg", ".png", ".jpeg")}
    summarize("실제 안개 + 불(FASDD 18장)", [stats(cv2.imread(str(byname[k]))) for k in fog_pos if k in byname])
    snow_pos = [k for k, v in meta.items() if v.get("kind") == "설경" and v.get("cls")]
    summarize("실제 설경 + 불(FASDD)", [stats(cv2.imread(str(byname[k]))) for k in rnd.sample(snow_pos, 120) if k in byname])
    hand = [l.strip() for l in open(TD / "handset_fire_hn_20260917/train.txt", encoding="utf-8") if l.strip()]
    summarize("맑은 CCTV 손라벨 프레임", [stats(cv2.imread(p)) for p in rnd.sample(hand, 150)])
    print("  --- 아래는 비교용(채점 편, 학습·튜닝에 안 씀)")
    summarize("채점 195 안개(90~130초)", [stats(f) for f in frames("C00_195_0001", range(90, 131, 5))])
    summarize("채점 216 눈(주간)", [stats(f) for f in frames("C00_216_0003", range(100, 131, 5))])
    summarize("채점 272 눈(야간)", [stats(f) for f in frames("C00_272_0003", range(100, 131, 5))])
    summarize("채점 012 맑음(주간)", [stats(f) for f in frames("C00_012_0007", range(200, 231, 5))])


if __name__ == "__main__":
    main()

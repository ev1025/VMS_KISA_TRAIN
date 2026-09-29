# -*- coding: utf-8 -*-
"""불이 안 나는 야간 CCTV 프레임을 하드네거티브로 모은다 (2026-09-24).

왜 (사용자 지시)
    f960_tier42_base_20260923 이 C00_089_0001(야간 공장)에서 0초부터 계속 울렸다.
    무엇을 불로 보는지 그려 보니 '어두운 바닥에 놓인 흰 물체'(종이·헝겊 뭉치)였다.
    0.34~0.39 로 200초 내내 울려 오검이 됐다.

    모델이 '야간 + 어두운 바닥 + 흰 덩어리 = 불' 로 배운 것이다.
    그런데 우리가 만든 흑백불 합성이 정확히 그 모양이라, 그대로 두면 더 나빠진다.
    반대쪽(불이 아닌 야간 흰 물체)을 같이 보여 줘야 한다.

어디서 가져오나
    kisa_연구개발_사람영상 825편 중 야간 136편. 사람 항목 영상이라 불이 안 난다.
    방화 모델 학습에 쓴 적이 없다(손라벨 빌더가 '모드다름' 으로 뺀다).
    라벨은 전부 빈 txt 다. 무엇이 있든 불은 아니다.

무엇을 고르나
    그냥 어두운 프레임만 모으면 까만 화면이라 배울 것이 없다.
    '어두운 배경에 밝은 덩어리가 있는' 프레임을 고른다. 089 가 그 모습이다.

사용
    python scripts/night_neg.py --name fire_nightneg_20260924 --n 4000
"""
import argparse
import glob
import json
import os
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
SRC = V / "data/원본데이터/kisa_연구개발_사람영상"


def 야간편():
    """XML 의 TimeOfDay 로 야간·새벽·해질녘 편을 고른다."""
    out = []
    for p in sorted(SRC.rglob("*.mp4")):
        x = p.with_suffix(".xml")
        if not x.is_file():
            continue
        try:
            w = ET.parse(x).getroot().find(".//Weather")
            tod = (w.findtext("TimeOfDay") or "").strip()
        except Exception:
            continue
        if tod in ("Night", "Dawn", "Dusk"):
            out.append(p)
    return out


def 밝은덩어리(fr, 어둡기=95):
    """어두운 화면에 밝은 덩어리가 있나. 089 가 그 모습이다."""
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    평균 = float(g.mean())
    if 평균 > 어둡기:
        return False, 평균, 0
    # 바탕보다 한참 밝은 덩어리
    # 089 는 '어두운 바닥 위에 또렷한 흰 덩어리' 다. 바탕보다 훨씬 밝고 작아야 한다.
    # 조건을 느슨하게 하면 그냥 어두운 복도만 잔뜩 모인다(2026-09-24 첫 판이 그랬다).
    바탕 = float(np.percentile(g, 60))
    m = (g > 바탕 + 70).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return False, 평균, 0
    큰 = int(st[1:, 4].max())
    # 너무 작으면 잡음, 너무 크면 조명 전체라 배울 것이 없다
    return 80 <= 큰 <= 12000, 평균, 큰


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="fire_nightneg_20260924")
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--per-clip", type=int, default=40)
    ap.add_argument("--step", type=float, default=4.0, help="몇 초마다 한 장 볼까")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    random.seed(a.seed)

    out = V / "data/학습데이터" / a.name
    (out / "images/train").mkdir(parents=True, exist_ok=True)
    (out / "labels/train").mkdir(parents=True, exist_ok=True)

    편 = 야간편()
    print("야간 편 %d개" % len(편))
    random.shuffle(편)

    만듦 = 0
    lines = []
    본편 = 0
    for p in 편:
        if 만듦 >= a.n:
            break
        cap = cv2.VideoCapture(str(p))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, int(round(fps * a.step)))
        이편 = 0
        for i in range(0, n, step):
            if 이편 >= a.per_clip or 만듦 >= a.n:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if not ok:
                continue
            좋음, 평균, 큰 = 밝은덩어리(fr)
            if not 좋음:
                continue
            stem = "%s_%05d" % (p.stem, i)
            cv2.imwrite(str(out / "images/train" / (stem + ".jpg")), fr,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            (out / "labels/train" / (stem + ".txt")).write_text("")
            lines.append(str((out / "images/train" / (stem + ".jpg")).resolve()))
            만듦 += 1
            이편 += 1
        cap.release()
        본편 += 1
        if 본편 % 10 == 0:
            print("  %d편 · %d장" % (본편, 만듦), flush=True)

    (out / "train.txt").write_text("\n".join(lines) + "\n")
    (out / "data.yaml").write_text(
        "path: %s\ntrain: train.txt\nval: train.txt\nnames:\n  0: fire\n  1: smoke\n" % out.resolve())
    (out / "meta.json").write_text(json.dumps({
        "name": a.name, "mode": "fire",
        "what": "불이 안 나는 야간 CCTV 프레임. 전부 빈 라벨(하드네거티브)",
        "왜": "C00_089_0001(야간 공장)에서 어두운 바닥의 흰 물체를 불로 보고 200초 내내 울렸다. "
              "흑백불 합성이 같은 모양이라 반대쪽을 같이 보여 줘야 한다",
        "출처": "kisa_연구개발_사람영상 야간 편(사람 항목 영상, 불 없음, 방화 학습 미사용)",
        "고른 기준": "평균 밝기 95 미만 + 바탕보다 45 밝은 덩어리가 30~40000px",
        "본 편": 본편, "장수": 만듦,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n%s  %d장 (야간 편 %d개에서)" % (out, 만듦, 본편))
    return 0


if __name__ == "__main__":
    sys.exit(main())

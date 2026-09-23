# -*- coding: utf-8 -*-
"""화면 밖으로 나간 사람 박스를 눈으로 볼 수 있게 그려서 모은다 (2026-09-23).

그리는 법
    흰 테두리 = 실제 영상 화면
    빨강      = 지금 라벨된 박스 (화면 밖까지 나가 있다)
    초록      = 화면 안으로 자른 것 (고치면 이렇게 된다)
    화면 밖이 보이게 둘레에 회색 여백을 붙인다.

사용: python scripts/dump_outbox.py <출력폴더> [장수]
"""
import collections
import glob
import json
import sys
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1])
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
PAD = 300

rows = json.load(open(V / "data/학습데이터/손라벨/person_labels.json", encoding="utf-8"))
밖 = []
for r in rows:
    if int(r.get("cls", -1)) < 0:
        continue
    x0, y0 = r["x"] - r["w"] / 2, r["y"] - r["h"] / 2
    x1, y1 = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    d = max(-x0, -y0, x1 - 1, y1 - 1)
    if d > 0.002:
        밖.append((d, r))
밖.sort(key=lambda z: -z[0])
print("화면 밖 박스 %d개" % len(밖))

# 한 클립에 몰리지 않게 클립당 최대 4장
뽑음 = collections.Counter()
고른것 = []
for d, r in 밖:
    if 뽑음[r["clip"]] >= 4:
        continue
    뽑음[r["clip"]] += 1
    고른것.append((d, r))
    if len(고른것) >= N:
        break

OUT.mkdir(parents=True, exist_ok=True)
영상캐시 = {}


def 영상(clip):
    if clip in 영상캐시:
        return 영상캐시[clip]
    p = None
    for c in glob.glob(str(V / "data/원본데이터/**" / (clip + ".mp4")), recursive=True):
        p = c
        break
    영상캐시[clip] = p
    return p


만듦 = 0
for d, r in 고른것:
    p = 영상(r["clip"])
    if not p:
        continue
    cap = cv2.VideoCapture(p)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(float(r["t"]) * fps))
    ok, f = cap.read()
    cap.release()
    if not ok:
        continue
    H, W = f.shape[:2]
    x0, y0 = int((r["x"] - r["w"] / 2) * W), int((r["y"] - r["h"] / 2) * H)
    x1, y1 = int((r["x"] + r["w"] / 2) * W), int((r["y"] + r["h"] / 2) * H)
    canvas = np.full((H + 2 * PAD, W + 2 * PAD, 3), 45, np.uint8)
    canvas[PAD:PAD + H, PAD:PAD + W] = f
    cv2.rectangle(canvas, (PAD, PAD), (PAD + W, PAD + H), (255, 255, 255), 2)
    cv2.rectangle(canvas, (PAD + x0, PAD + y0), (PAD + x1, PAD + y1), (0, 0, 255), 3)
    cv2.rectangle(canvas, (PAD + max(0, x0), PAD + max(0, y0)),
                  (PAD + min(W, x1), PAD + min(H, y1)), (0, 255, 0), 3)
    cv2.putText(canvas, "%s  t=%s  %dx%d px  %.0f%% 밖" % (r["clip"], r["t"], x1 - x0, y1 - y0, d * 100),
                (PAD, PAD - 25), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    cv2.putText(canvas, "red = now   green = clipped   white = frame",
                (PAD, PAD + H + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    cv2.imwrite(str(OUT / ("%03d_%s_t%s.jpg" % (int(d * 100), r["clip"], r["t"]))), canvas)
    만듦 += 1

c = collections.Counter()
for d, r in 밖:
    x0, y0 = r["x"] - r["w"] / 2, r["y"] - r["h"] / 2
    x1, y1 = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    if x0 < -0.002: c["왼쪽"] += 1
    if x1 > 1.002: c["오른쪽"] += 1
    if y0 < -0.002: c["위"] += 1
    if y1 > 1.002: c["아래"] += 1
클립 = collections.Counter(r["clip"] for _, r in 밖)

(OUT / "설명.txt").write_text(
    "화면 밖으로 나간 사람 박스 (2026-09-23)\n"
    "=======================================\n\n"
    "그림 보는 법\n"
    "  흰 테두리 = 실제 영상 화면\n"
    "  빨강      = 지금 라벨된 박스. 화면 밖까지 나가 있다\n"
    "  초록      = 화면 안으로 자른 것. 고치면 이렇게 된다\n"
    "  파일 이름 앞 숫자 = 몇 %% 가 화면 밖인지\n\n"
    "무엇이 문제인가\n"
    "  YOLO 라벨 좌표는 0~1 안이어야 한다. 벗어나면 박스 중심이 실제 사람보다\n"
    "  위로(또는 옆으로) 밀린다. 위 그림에서 빨강 박스의 중심은 사람 머리 위 허공이고,\n"
    "  초록 박스의 중심이 실제 사람이다.\n\n"
    "왜 생겼나\n"
    "  사람을 그리다 드래그가 화면 경계를 넘어간 것이다.\n\n"
    "얼마나 되나\n"
    "  전체 %d개\n  방향: %s\n  클립별 상위: %s\n\n"
    "고치는 법\n"
    "  화면 안으로 자르기만 하면 된다(초록). 사람이 실제로 보이는 범위는 화면 안뿐이라\n"
    "  정보가 사라지지 않는다. scripts/clean_fire_labels.py 와 같은 방식이다.\n"
    % (len(밖), dict(c), 클립.most_common(6)),
    encoding="utf-8")
print("%d장 그림 · %s" % (만듦, OUT))

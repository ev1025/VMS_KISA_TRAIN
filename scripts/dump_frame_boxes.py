# -*- coding: utf-8 -*-
"""덤프의 박스를 원본 프레임 위에 그려서 저장한다. 모델 비교용(배포 vs 손라벨).

왜 (2026-09-18)
    손라벨 모델은 배회 구역에서 사람을 배포 모델보다 4~27초 먼저 잡는다(loiter_fp_timeline).
    그게 '진짜 먼저 본 것' 인지 '박스가 커서 구역에 먼저 걸린 것' 인지는 프레임을 봐야 안다.

사용
    python scripts/dump_frame_boxes.py <출력폴더> <편> <초> [<초> ...]
    예) python scripts/dump_frame_boxes.py /tmp/kisa_frames C00_232_0001 105 110 117.5
색: 배포 = 초록 · 손라벨 32.6% = 주황 · 손라벨 10.8% = 하늘. 구역 = 노란 선.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["loitering"]
DUMPS = [("deploy", "dumps/loiter_botsort_v2", (80, 220, 80)),
         ("hand32", "dumps/loiter_p1280hand_bs1280", (60, 140, 255)),
         ("hand10", "dumps/loiter_p1280ov2_bs1280", (255, 200, 60))]


def nearest_row(rows, t):
    return min(rows, key=lambda r: abs(r["t"] - t))


out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
stem = sys.argv[2]
times = [float(x) for x in sys.argv[3:]]
vid = next((p for p in KP.videos("배회").rglob(stem + ".*") if p.suffix.lower() != ".xml"), None)
if vid is None:
    sys.exit("영상 없음: " + stem)
poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (1280, 720))
dumps = []
for name, d, col in DUMPS:
    f = Path(d) / (stem + ".jsonl")
    if f.is_file():
        dumps.append((name, [json.loads(l) for l in f.read_text().splitlines()], col))

cap = cv2.VideoCapture(str(vid))
fps = cap.get(cv2.CAP_PROP_FPS) or 30
for t in times:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
    ok, frame = cap.read()
    if not ok:
        print("프레임 실패", stem, t); continue
    frame = cv2.resize(frame, (1280, 720))
    pts = [(int(x), int(y)) for x, y in poly]
    cv2.polylines(frame, [np.array(pts, dtype=np.int32)], True, (0, 230, 230), 2)
    y0 = 24
    for name, rows, col in dumps:
        r = nearest_row(rows, t)
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if conf < 0.25:
                continue
            inside = K.entered((x1, y1, x2, y2), poly, CFG["corners"])
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), col, 2 if inside else 1)
            cv2.putText(frame, "%s %s %.2f%s" % (name, pid, conf, "*" if inside else ""), (int(x1), max(12, int(y1) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
        cv2.putText(frame, "%s: t=%.1f rows %d boxes" % (name, r["t"], len(r["boxes"])), (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)
        y0 += 22
    cv2.putText(frame, "%s  t=%.1fs  (* = zone)" % (stem, t), (10, 710), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    p = out / ("%s_%05.1f.jpg" % (stem, t))
    cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("저장", p)

# -*- coding: utf-8 -*-
"""쓰러짐을 연구개발 330편으로 확장 평가한다. 배포 경로(FallJudge) 그대로 돌려 창 점수를 덤프한다.

왜 (2026-09-18)
    지금 쓰러짐 100.00 은 배포 검증영상 10편으로 낸 값이다. 10편에서 10/10 이어도
    실제 성공률의 95% 신뢰구간은 74~100% 다. 연구개발 쓰러짐 330편에는 정답 XML 이
    전부 있으므로 33배 큰 검증셋으로 다시 잴 수 있다.

덤프를 남기는 이유
    창 점수(curves)만 파일로 두면 판정 규칙(th·need)은 추론 없이 훑을 수 있다.
    scripts/fall_sweep.py 가 그 덤프를 읽는다. dumps/fall_seq_1280 과 같은 형식이다.

이어서 돌기
    편마다 파일 하나를 쓴다. 이미 있는 편은 건너뛰므로 중간에 끊겨도 다시 돌리면 이어진다.

사용
    python scripts/fall_dump_all.py [--out dumps/fall_seq_dev330] [--limit N] [--imgsz 1280]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import cv2                      # noqa: E402
import kisa_items as K          # noqa: E402

SRC = Path(__import__("os").environ.get("FALL_SRC",
           str(V / "data/원본데이터/kisa_연구개발_사람영상/4. 쓰러짐(330개)")))   # Thor 는 FALL_SRC 로 바꿔 쓴다

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="dumps/fall_seq_dev330")
ap.add_argument("--limit", type=int, default=0, help="앞 N 편만(시험용)")
ap.add_argument("--imgsz", type=int, default=None, help="자세 해상도. 기본은 배포 설정")
a = ap.parse_args()

CFG = K.ITEMS["falldown"]
IMGSZ = a.imgsz or CFG.get("pose_imgsz", 1280)
OUT = V / a.out
OUT.mkdir(parents=True, exist_ok=True)
K.WEIGHTS = Path(__import__("os").environ.get("FALL_W", str(V / "_kisa_port/weights/kisa")))


def gt_of(xml):
    """정답 XML 에서 첫 경보 시각(초). K.read_alarms 와 같은 값을 쓴다."""
    try:
        al = K.read_alarms(str(xml))
        return al[0]["start_s"] if al else None
    except Exception:
        return None


mp4s = sorted(SRC.glob("*.mp4"))
if a.limit:
    mp4s = mp4s[:a.limit]
todo = [p for p in mp4s if not (OUT / (p.stem + ".json")).is_file()]
print("쓰러짐 확장 평가 · 전체 %d편 · 남은 %d편 · 자세 해상도 %d · 주기 %.1f초"
      % (len(mp4s), len(todo), IMGSZ, CFG["stride"]), flush=True)
if not todo:
    print("이미 다 떴다. scripts/fall_sweep.py 로 규칙을 훑으면 된다.")
    raise SystemExit(0)

t0 = time.time()
for n, mp4 in enumerate(todo, 1):
    stem = mp4.stem
    gt = gt_of(mp4.with_suffix(".xml"))
    judge = K.FallJudge(K.WEIGHTS / CFG["model"], K.WEIGHTS / "fall_track.pt",
                        1.1, CFG["need"], device=0, pose_imgsz=IMGSZ)   # th 1.1 = 판정은 끄고 곡선만 모은다
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = CFG["stride"]
    t = 0.0
    while True:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, fr = cap.read()
        if not ok:
            break
        judge.feed(t, fr)
        t += step
    cap.release()
    curves = [tr["curve"] for tr in judge.tracks if tr.get("curve")]
    (OUT / (stem + ".json")).write_text(
        json.dumps({"imgsz": IMGSZ, "fps": fps, "gt": gt, "curves": curves}, ensure_ascii=False),
        encoding="utf-8")
    el = time.time() - t0
    eta = el / n * (len(todo) - n)
    print("  [%3d/%3d] %-16s 트랙 %3d개 · 정답 %s · 경과 %.1f시간 · 남음 %.1f시간"
          % (n, len(todo), stem, len(curves), gt, el / 3600, eta / 3600), flush=True)

print("끝. 규칙 훑기: python scripts/fall_sweep.py %s" % a.out)

# -*- coding: utf-8 -*-
"""쓰러짐: 자세 검출 해상도·신뢰도를 바꿔 트랙 분절과 정답 부근 점수가 달라지는지 본다.

가설: 실패한 두 편(235 미검 0.238 / 034 오검 0.114)은 문턱 문제가 아니라 입력 문제다.
      정검 8편은 전부 0.96 이상으로 확신 있게 맞히는데 이 둘만 다른 세계에 있다.
      235 는 트랙이 131개로 쪼개져 10초 창에 낙상 전체가 담기지 못했을 가능성이 크다.
      자세 검출이 흔들려서 트랙이 끊긴다면, 해상도를 올리면 분절이 줄고 점수가 오를 것이다.

FallJudge 는 imgsz 640 · conf 0.10 이 박혀 있으므로 predict 를 감싸서 덮어쓴다.
사용: python fall_res.py <클립stem> <GT초> <imgsz> [conf]
"""
import math
import sys
from pathlib import Path

import cv2

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_paths as KP           # noqa: E402
import kisa_items as K            # noqa: E402


def run(stem, gt, imgsz, conf):
    cfg = K.ITEMS["falldown"]
    judge = K.FallJudge(K.WEIGHTS / cfg["model"], K.WEIGHTS / "fall_track.pt", 1.1, cfg["need"])
    orig = judge.pose.predict                       # imgsz·conf 를 강제로 바꿔 끼운다
    judge.pose.predict = lambda *a, **kw: orig(*a, **{**kw, "imgsz": imgsz, "conf": conf})

    mp4 = KP.find_mp4(stem)
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * cfg["stride"]))
    i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                judge.feed(i / fps, fr)
        i += 1
    cap.release()

    curves = [tr["curve"] for tr in judge.tracks if tr.get("curve")]
    near = [1.0 / (1.0 + math.exp(-z)) for cur in curves for t, z in cur if abs(t - gt) <= 5]
    peak = max(near) if near else 0.0
    # 연속 4창 돌파가 정답 창 안에서 일어나는지도 본다
    fired = None
    for cur in curves:
        run_ = 0
        for k, (t, z) in enumerate(cur):
            p = 1.0 / (1.0 + math.exp(-z))
            run_ = run_ + 1 if p >= cfg["th"] else 0
            if run_ >= cfg["need"]:
                t0 = cur[k - cfg["need"] + 1][0]
                fired = t0 if fired is None else min(fired, t0)
                break
    ok_win = fired is not None and gt - 2 <= fired <= gt + 10
    print(f"  {stem[4:]:<12} imgsz={imgsz:<5} conf={conf:<5} 트랙 {len(curves):>4}개  "
          f"정답부근 최고점수 {peak:.3f}  발화 {('%.1f' % fired) if fired else '없음':>7}  "
          f"{'정답창 안' if ok_win else ('발화없음' if fired is None else '창 밖')}", flush=True)


if __name__ == "__main__":
    run(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]),
        float(sys.argv[4]) if len(sys.argv) > 4 else 0.10)

# -*- coding: utf-8 -*-
"""쓰러짐 미검 진단: 정답 시각 부근에서 SeqNet 점수가 문턱을 얼마나 못 넘는지 본다.

판정은 '트랙별 10초 창 점수 p >= th 가 need 창 연속'이다. 그래서 실패는 셋 중 하나다.
  (1) 자세 모델이 사람을 못 잡아 트랙이 없다      → 트랙 0개로 나온다
  (2) 트랙은 있는데 점수가 문턱 근처에도 못 간다   → 특징·모델 한계
  (3) 점수는 넘는데 연속(need)이 안 채워진다       → 파라미터로 해결 가능
사용: python fall_probe.py <mp4> <GT초>
"""
import math
import sys
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_items as K            # noqa: E402


def main(mp4, gt):
    cfg = K.ITEMS["falldown"]
    judge = K.FallJudge(K.WEIGHTS / cfg["model"], K.WEIGHTS / "fall_track.pt",
                        cfg["th"], cfg["need"])
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

    th = cfg["th"]
    print(f"\n[{Path(mp4).stem}] GT {gt}초 · 문턱 p>={th} · 연속 {cfg['need']}창 필요")
    print(f"  트랙 {len(judge.tracks)}개 · 최종 판정 {judge.decided}")
    near = []
    for n, tr in enumerate(judge.tracks):
        cur = tr.get("curve") or []
        if not cur:
            continue
        # 정답 시각 ±15초 구간의 점수
        seg = [(t, 1.0 / (1.0 + math.exp(-z))) for t, z in cur if abs(t - gt) <= 15]
        if not seg:
            continue
        best_t, best_p = max(seg, key=lambda x: x[1])
        over = sum(1 for _, p in seg if p >= th)
        near.append((best_p, n, best_t, over, len(seg)))
    if not near:
        print("  ⚠ 정답 시각 부근에 평가된 트랙 창이 없다 → 검출·트랙 단계 실패")
        return
    near.sort(reverse=True)
    print("  정답 부근(±15초) 트랙별 최고 점수:")
    for best_p, n, best_t, over, ntot in near[:5]:
        mark = "문턱 넘음" if best_p >= th else "문턱 미달"
        print(f"    트랙{n:>3}  최고 p={best_p:.3f} @{best_t:>6.1f}초  "
              f"넘은 창 {over}/{ntot}  {mark}")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]))

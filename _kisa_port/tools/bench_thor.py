# -*- coding: utf-8 -*-
"""Thor(배포 장비)에서 네 항목의 한 표본당 처리 시간을 잰다.

왜 (2026-09-16)
    docs/kisa/KISA_시험_체크리스트.md 의 표는 2026-09-15 값이라 그 뒤 바뀐 둘이 빠져 있다.
      방화   표는 640 · 6뷰 · 가중치 1벌. 지금은 640+960 · 6뷰 · 2벌(앙상블)
      쓰러짐 표는 자세 640. 실제 설정은 1280 이라 픽셀이 4배다. 주기가 100ms 라 가장 빠듯하다
    설정은 이 장비의 tools/kisa_items.py 에서 그대로 읽는다(손으로 옮겨 적지 않는다).

무엇을 재나
    배포 경로가 표본마다 실제로 부르는 것을 그대로 부른다.
      방화   FireJudge.feed        (6뷰 x 가중치 수, 낱장 추론)
      쓰러짐 FallJudge.feed        (자세 1장 + 5호출마다 SeqNet)
      침입   PersonDetector.detect + Tracker.update   (3x3 타일)
      배회   BotSortPersons.update (전체 프레임)
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "/kisa/tools")
import kisa_items as K   # noqa: E402

N_WARM, N_RUN = 3, int(sys.argv[1]) if len(sys.argv) > 1 else 15
VID = Path("/data/영상")
ITEM_DIR = {"방화": "fire", "침입": "intrusion", "배회": "loitering", "쓰러짐": "falldown"}


def frames(item, n):
    """그 항목 영상에서 서로 다른 프레임 n 장. 실제 해상도 그대로."""
    d = VID / ITEM_DIR[item]
    mp4 = next(iter(sorted(d.glob("*.mp4"))), None)
    if mp4 is None:
        return []
    cap = cv2.VideoCapture(str(mp4))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 3000
    out = []
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (0.3 + 0.4 * i / max(1, n - 1))))
        ok, fr = cap.read()
        if ok:
            out.append(fr)
    cap.release()
    return out


def timeit(call, imgs):
    for im in imgs[:N_WARM]:
        call(im)
    ts = []
    for im in imgs:
        t0 = time.perf_counter()
        call(im)
        ts.append((time.perf_counter() - t0) * 1000.0)
    ts.sort()
    return ts[len(ts) // 2], ts[-1]          # 중앙값, 최악


def line(item, views, ms, worst, budget_ms, note):
    print(f"  {item:<7}{views:>4}뷰 {ms:>8.1f}ms  최악 {worst:>7.1f}ms  주기 {budget_ms:>5.0f}ms"
          f"  여유 {budget_ms / ms:>6.2f}배   {note}")


print(f"Thor 표본당 처리 시간  (표본 {N_RUN}장, 예열 {N_WARM}장, 중앙값)\n")
W = Path("/kisa/weights/kisa")
K.WEIGHTS = W

# ---- 방화 : 지금 배포 구성 그대로 (앙상블이면 2벌)
c = K.ITEMS["fire"]
ws = K.fire_weights(c)
j = K.FireJudge(ws, c, device=0)
imgs = frames("방화", N_RUN)


def fire(im):
    j.decided = None
    j.feed(0.0, im)


ms, wo = timeit(fire, imgs)
note = " + ".join(f"{Path(p).name}@{z}" for p, z in ws)
line("방화", 6 * len(ws), ms, wo, c["stride"] * 1000, note)

# ---- 쓰러짐 : 설정의 자세 해상도 그대로
c = K.ITEMS["falldown"]
z = c.get("pose_imgsz", 640)
fj = K.FallJudge(W / c["model"], W / "fall_track.pt", c["th"], c["need"], device=0, pose_imgsz=z)
imgs = frames("쓰러짐", max(N_RUN, 10))


def fall(im):
    fj.decided = None
    fj.feed(fj.i * 0.1, im)


ms, wo = timeit(fall, imgs)
line("쓰러짐", 1, ms, wo, c["stride"] * 1000, f"자세 {z} + SeqNet(5호출마다)")

# ---- 침입 : 3x3 타일 + 트래커
c = K.ITEMS["intrusion"]
det = K.PersonDetector(W / c["model"], device=0, contain=None)
tr = K.Tracker()
imgs = frames("침입", N_RUN)
ms, wo = timeit(lambda im: tr.update(det.detect(im)), imgs)
line("침입", K.TILE["grid"] ** 2, ms, wo, c["stride"] * 1000, f"타일 {K.TILE['grid']}x{K.TILE['grid']}@{K.TILE['imgsz']}")

# ---- 배회 : 전체 프레임 + BoT-SORT
c = K.ITEMS["loitering"]
bs = K.BotSortPersons(W / c["model"], device=0, imgsz=c.get("track_imgsz", 640))
imgs = frames("배회", N_RUN)
ms, wo = timeit(bs.update, imgs)
line("배회", 1, ms, wo, c["stride"] * 1000, f"전체프레임@{c.get('track_imgsz', 640)} BoT-SORT")

print("\n  여유 1배 미만이면 실시간에 못 맞춘다. 최악값도 주기 안에 들어와야 안전하다.")

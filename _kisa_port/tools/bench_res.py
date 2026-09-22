# -*- coding: utf-8 -*-
"""Thor 에서 침입·배회를 해상도별로 재서 1280 배포가 실시간에 들어오는지 본다.

왜 (2026-09-17)
    "평가는 학습 해상도로" 를 확정했다. 그러면 1280 으로 학습한 사람 모델은 배포도 1280 이어야 한다.
    침입은 3x3 타일이라 타일당 픽셀이 960 -> 1280 에서 1.78배가 된다. 먼저 들어오는지부터 본다.

제출 도구는 건드리지 않는다. 설정을 읽어 쓰기만 하고, 해상도만 이 자리에서 바꿔 잰다.
사용:  python3 tools/bench_res.py [표본수]
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, "/kisa/tools")
import kisa_items as K   # noqa: E402

N_WARM = 3
N_RUN = int(sys.argv[1]) if len(sys.argv) > 1 else 15
VID = Path("/data/영상")
W = Path("/kisa/weights/kisa")
K.WEIGHTS = W
SIZES = (640, 960, 1280)


def frames(sub, n):
    """그 항목 영상에서 서로 다른 프레임 n 장. 실제 해상도 그대로."""
    mp4 = next(iter(sorted((VID / sub).glob("*.mp4"))), None)
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
    return ts[len(ts) // 2], ts[-1]


def show(item, z, ms, worst, budget_ms, now):
    mark = "  <- 지금 배포" if now else ""
    ok = "" if budget_ms / ms >= 1.0 else "   못 들어옴"
    print("  %-5s %5d  %8.1fms  최악 %7.1fms  주기 %4.0fms  여유 %5.2f배%s%s"
          % (item, z, ms, worst, budget_ms, budget_ms / ms, mark, ok), flush=True)


print("Thor 해상도별 처리 시간  (표본 %d장, 예열 %d장, 중앙값)\n" % (N_RUN, N_WARM))
print("  항목  해상도      중앙값         최악      주기    여유")

# ---- 침입 : 3x3 타일 + 트래커. TILE 은 전역이라 잰 뒤 되돌린다
c = K.ITEMS["intrusion"]
imgs = frames("intrusion", N_RUN)
keep = K.TILE["imgsz"]
for z in SIZES:
    K.TILE["imgsz"] = z
    det = K.PersonDetector(W / c["model"], device=0, contain=None)
    tr = K.Tracker()
    ms, wo = timeit(lambda im: tr.update(det.detect(im)), imgs)
    show("침입", z, ms, wo, c["stride"] * 1000, z == keep)
K.TILE["imgsz"] = keep

# ---- 배회 : 전체 프레임 + BoT-SORT
c = K.ITEMS["loitering"]
imgs = frames("loitering", N_RUN)
now = c.get("track_imgsz", 640)
for z in SIZES:
    bs = K.BotSortPersons(W / c["model"], device=0, imgsz=z)
    ms, wo = timeit(bs.update, imgs)
    show("배회", z, ms, wo, c["stride"] * 1000, z == now)

print("\n  여유 1배 미만이면 실시간에 못 맞춘다. 최악값도 주기 안에 들어와야 안전하다.")
print("  침입은 3x3 타일이라 해상도를 올리면 타일마다 무거워진다(960->1280 은 픽셀 1.78배).")

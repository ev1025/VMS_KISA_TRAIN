# -*- coding: utf-8 -*-
"""Thor 에서 방화를 해상도·벌수별로 재서 1280 배포가 실시간에 들어오는지 본다.

왜 (2026-09-17)
    사람(침입·배회)은 1280 여유를 확인했지만 방화는 안 쟀다.
    방화는 표본마다 6뷰를 낱장으로 돌리고 지금은 가중치가 2벌이라 12번 추론한다.
    해상도를 올리면 그 12번이 전부 무거워지므로 사람보다 훨씬 빠듯할 수 있다.
    학습이 이겨도 속도가 안 되면 쓸 수 없으니 먼저 본다.

제출 도구는 건드리지 않는다. 설정을 읽어 쓰기만 하고 해상도만 이 자리에서 바꿔 잰다.
사용:  python3 tools/bench_fire_res.py [표본수]
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, "/kisa/tools")
import kisa_items as K   # noqa: E402

N_WARM = 3
N_RUN = int(sys.argv[1]) if len(sys.argv) > 1 else 12
VID = Path("/data/영상/fire")
W = Path("/kisa/weights/kisa")
K.WEIGHTS = W
C = K.ITEMS["fire"]
BUDGET = C["stride"] * 1000.0          # 표본 주기(ms). 방화는 0.5초 = 500ms


def frames(n):
    mp4 = next(iter(sorted(VID.glob("*.mp4"))), None)
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


def timeit(judge, imgs):
    def call(im):
        judge.decided = None
        judge.feed(0.0, im)
    for im in imgs[:N_WARM]:
        call(im)
    ts = []
    for im in imgs:
        t0 = time.perf_counter()
        call(im)
        ts.append((time.perf_counter() - t0) * 1000.0)
    ts.sort()
    return ts[len(ts) // 2], ts[-1]


def run(label, ws, imgs, now=False):
    j = K.FireJudge(ws, C, device=0)
    ms, wo = timeit(j, imgs)
    ok = "" if BUDGET / ms >= 1.0 else "   못 들어옴"
    print("  %-34s %8.1fms  최악 %7.1fms  여유 %5.2f배%s%s"
          % (label, ms, wo, BUDGET / ms, "  <- 지금 배포" if now else "", ok), flush=True)


imgs = frames(N_RUN)
if not imgs:
    raise SystemExit("영상이 없다: %s" % VID)

dep = K.fire_weights(C)                 # 지금 배포 (가중치 2벌, 640 + 960)
m1 = dep[0][0]
m2 = dep[1][0] if len(dep) > 1 else None

print("Thor 방화 표본당 처리 시간  (표본 %d장, 예열 %d장, 중앙값, 주기 %.0fms)" % (N_RUN, N_WARM, BUDGET))
print("방화는 표본마다 6뷰를 낱장으로 돈다. 2벌이면 12번이다.\n")
print("  %-34s %10s %13s %10s" % ("구성", "중앙값", "최악", "여유"))

run("배포 2벌 (%d + %d)" % (dep[0][1], dep[1][1] if m2 else 0), dep, imgs, now=True)
print()
for z in (640, 960, 1280):
    run("단독 %s @%d" % (m1.name, z), [(m1, z)], imgs)
if m2:
    print()
    for z in (640, 960, 1280):
        run("단독 %s @%d" % (m2.name, z), [(m2, z)], imgs)
    print()
    run("2벌 둘 다 @1280", [(m1, 1280), (m2, 1280)], imgs)
    run("2벌 640 + 1280", [(m1, 640), (m2, 1280)], imgs)

print("\n  여유 1배 미만이면 실시간에 못 맞춘다. 최악값도 주기 안에 들어와야 안전하다.")
print("  1280 학습이 이겨도 여기서 1배를 못 넘으면 배포할 수 없다.")

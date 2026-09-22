# -*- coding: utf-8 -*-
"""배회 한 편을, 가중치만 바꿔 배포 경로 그대로 돌려 4단계로 가른다.

왜 (2026-09-18)
    검수 화면에서 박스가 보인다고 정검이 되는 것이 아니다. 배회 판정은
    '구역 안 · 신뢰도 문턱 넘음 · 같은 트랙 ID 로 체류 N초' 를 모두 요구한다.
    눈으로 보이는 박스와 판정이 요구하는 조건이 어디서 갈리는지 숫자로 본다.

사용
    python scripts/loiter_one.py <가중치.pt> <클립stem> [클립stem ...]
"""
import sys
from collections import defaultdict
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import cv2                                   # noqa: E402
import kisa_items as K                       # noqa: E402
import kisa_paths as KP                      # noqa: E402

CFG = K.ITEMS["loitering"]
W = Path(sys.argv[1])
STEMS = sys.argv[2:]
if not W.is_file() or not STEMS:
    raise SystemExit("사용: python scripts/loiter_one.py <가중치.pt> <클립stem> ...")

print("가중치 %s · 추적 해상도 %s · 문턱 %.2f · 체류 %.1f초 · 꼭짓점 %d"
      % (W.name, CFG.get("track_imgsz", 640), CFG["conf"], CFG["dwell"], CFG["corners"]))
print("%-16s %6s %8s %8s %9s %9s %8s %s"
      % ("클립", "GT", "검출", "구역안", "문턱통과", "최장체류", "트랙수", "판정"))

for stem in STEMS:
    mp4 = next(KP.videos("배회").rglob(stem + ".mp4"), None)
    if mp4 is None:
        print("%-16s (영상 없음)" % stem); continue
    xml = next(KP.videos("배회").rglob(stem + ".xml"), None)
    gt = (K.read_alarms(xml) or [{}])[0].get("start_s") if xml else None

    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (1280, 720))
    bs = K.BotSortPersons(W, device=0, imgsz=CFG.get("track_imgsz", 640))

    stride = CFG["stride"]
    n_det = n_in = n_conf = 0
    dwell = defaultdict(float)               # 트랙 ID 별 누적 체류
    last_t = {}
    ids = set()
    t = 0.0
    while True:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, fr = cap.read()
        if not ok:
            break
        for pid, conf, x1, y1, x2, y2 in bs.update(fr):
            n_det += 1
            if not K.entered((x1, y1, x2, y2), poly, CFG["corners"]):
                continue
            n_in += 1
            if conf < CFG["conf"]:
                continue
            n_conf += 1
            ids.add(pid)
            # 끊김이 gap 보다 크면 체류를 다시 센다(배포 규칙과 같은 취급)
            if pid in last_t and t - last_t[pid] > CFG["gap"]:
                dwell[pid] = 0.0
            dwell[pid] += stride
            last_t[pid] = t
        t += stride
    cap.release()

    best = max(dwell.values()) if dwell else 0.0
    verdict = "체류 채움 → 경보 가능" if best >= CFG["dwell"] else (
        "구역 안 검출 없음" if n_in == 0 else
        "문턱 미달" if n_conf == 0 else "체류 부족")
    print("%-16s %6s %8d %8d %9d %8.1f초 %7d  %s"
          % (stem, gt, n_det, n_in, n_conf, best, len(ids), verdict))

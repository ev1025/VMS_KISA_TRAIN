# -*- coding: utf-8 -*-
"""가중치가 '못 잡는 편' 의 영역 안 사람을 얼마나 확신하는지 잰다.

왜 이 지표인가 (2026-09-16)
    손라벨만으로 학습한 모델은 배경을 모르니 오검이 터져 F1 이 40점대로 나온다.
    그 절대 점수로는 손라벨이 일을 하는지 알 수 없다.
    우리가 못 잡는 세 편은 전부 '영역 안 최고 신뢰도 < 문턱' 에서 걸린다.
    그러니 그 숫자 하나가 오르는지만 보면 된다. F1 은 COCO 와 섞으면 따라온다.

사용
    python scripts/zone_conf.py <가중치.pt> [클립...]
    (클립을 안 주면 침입 미검 3편을 본다)
"""
import sys
from pathlib import Path

import cv2

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["intrusion"]
MISS = ["C00_249_0003", "C00_255_0001", "C00_275_0001"]
PAD = 15.0          # GT 앞뒤 몇 초를 볼 것인가


def gt_of(stem):
    g = next(KP.videos("침입").rglob(stem + ".xml"), None)
    a = K.read_alarms(g) if g else []
    return a[0]["start_s"] if a else None


def probe(weights, stem, imgsz):
    det = K.PersonDetector(weights, device=0, contain=None)
    poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (1280, 720))
    gt = gt_of(stem)
    cap = cv2.VideoCapture(str(KP.find_mp4(stem)))
    best_in = best_any = 0.0
    n_in = 0
    at = None
    t = max(0.0, gt - PAD)
    while t <= gt + PAD:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, im = cap.read()
        if ok:
            for conf, x1, y1, x2, y2 in det.detect(im):
                best_any = max(best_any, conf)
                if K.entered((x1, y1, x2, y2), poly, CFG["corners"]):
                    n_in += 1
                    if conf > best_in:
                        best_in, at = conf, round(t, 1)
        t += KP.SAMPLE_STRIDE_S
    cap.release()
    return gt, best_in, at, n_in, best_any


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    w = Path(sys.argv[1]).resolve()
    stems = sys.argv[2:] or MISS
    z = int(K.TILE["imgsz"])
    print(f"가중치 {w.name}   타일 {K.TILE['grid']}x{K.TILE['grid']}@{z}   문턱 {CFG['conf']}")
    print(f"{'클립':<16}{'GT':>6}{'영역안 최고':>12}{'그 시각':>9}{'영역안 표본':>12}{'화면전체 최고':>14}")
    for s in stems:
        gt, bi, at, n, ba = probe(w, s, z)
        mark = "  <== 문턱 넘음" if bi >= CFG["conf"] else ""
        print(f"{s:<16}{gt:>6}{bi:>12.3f}{str(at):>9}{n:>12}{ba:>14.3f}{mark}")


if __name__ == "__main__":
    main()

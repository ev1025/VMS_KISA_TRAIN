# -*- coding: utf-8 -*-
"""항목별 추론 속도 측정: 해상도 × 장치(GPU/CPU) 로 프레임당 소요와 실시간 여유를 잰다.

왜 필요한가: 해상도를 올리면 점수가 오르지만(쓰러짐 84.21→90.00) 연산이 늘어난다.
  시험은 RTSP 실시간이라 표본 주기 안에 처리를 못 끝내면 프레임을 놓쳐 점수가 무너진다.
  항목마다 표본 주기가 다르다(쓰러짐 0.1초 · 나머지 0.5초)므로 여유율을 항목 기준으로 계산한다.

주의(2026-09-16): 이 도구는 순수 추론만 잰다. 타일 대신 원본 프레임을 뷰 수만큼 복제해
  한 배치로 넣고 NMS·트래커·SeqNet·판정기를 뺀다. 그래서 배포 경로와 값이 다르다
  (침입은 과대, 배회는 과소). 배포 여유를 알고 싶으면 _kisa_port/tools/bench_thor.py 를
  Thor 에서 돌린다. 두 표를 섞어 읽지 말 것.

출력: dumps/bench_items.json  {항목: [{device, imgsz, ms, fps, budget_ms, headroom}]}
사용: python bench_items.py [--frames 60]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_paths as KP           # noqa: E402
import kisa_items as K            # noqa: E402

OUT = V / "dumps/bench_items.json"

# 항목 → (가중치 파일, 표본 주기 초, 한 표본에 추론하는 뷰 수, 재볼 해상도)
#   방화는 6뷰 타일, 침입은 3x3=9타일, 배회·쓰러짐은 전체 프레임 1장
PLAN = {
    "방화": ("fire_snowfull.pt", 0.5, 6, (640, 960)),
    "침입": ("person_v3.pt", 0.5, 9, (960, 1280)),
    "배회": ("person_v2.pt", 0.5, 1, (640, 960, 1280)),
    "쓰러짐": ("yolo11x-pose.pt", 0.1, 1, (640, 960, 1280)),
}


def sample_frame(item):
    """그 항목의 배포 영상에서 프레임 한 장. 실제 해상도(1280x720)로 재야 의미가 있다."""
    mp4 = next(iter(sorted(KP.videos(item).glob("*.mp4"))), None)
    cap = cv2.VideoCapture(str(mp4))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 300)
    ok, fr = cap.read()
    cap.release()
    return fr if ok else np.zeros((720, 1280, 3), np.uint8)


def bench(model, frame, imgsz, device, views, n):
    from ultralytics import YOLO
    m = YOLO(str(model))
    crops = [frame] * views                       # 뷰 수만큼 같은 크기로 넣어 배치 효과까지 반영
    for _ in range(3):                            # 예열(첫 호출은 커널 컴파일 때문에 느리다)
        m.predict(crops, imgsz=imgsz, conf=0.1, verbose=False, device=device)
    t0 = time.perf_counter()
    for _ in range(n):
        m.predict(crops, imgsz=imgsz, conf=0.1, verbose=False, device=device)
    return (time.perf_counter() - t0) / n * 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=20)
    ap.add_argument("--cpu", action="store_true", help="CPU 도 함께 잰다(느리다)")
    a = ap.parse_args()

    out = {}
    for item, (wname, stride, views, sizes) in PLAN.items():
        w = K.WEIGHTS / wname
        if not w.is_file():
            print(f"  {item}: 가중치 없음 {wname}"); continue
        frame = sample_frame(item)
        budget = stride * 1000.0
        rows = []
        devices = ["0"] + (["cpu"] if a.cpu else [])
        for dev in devices:
            for z in sizes:
                try:
                    ms = bench(w, frame, z, dev, views, a.frames if dev == "0" else max(3, a.frames // 6))
                except Exception as e:
                    print(f"  {item} {dev} {z}: 실패 {type(e).__name__} {e}"); continue
                rows.append({"device": "GPU" if dev == "0" else "CPU", "imgsz": z,
                             "ms": round(ms, 1), "fps": round(1000.0 / ms, 1),
                             "budget_ms": budget, "headroom": round(budget / ms, 2)})
                r = rows[-1]
                print(f"  {item:<5} {r['device']:<3} imgsz={z:<5} {r['ms']:>7.1f}ms/표본 "
                      f"({views}뷰) · 주기 {budget:.0f}ms · 여유 {r['headroom']:.2f}배", flush=True)
        out[item] = {"stride_s": stride, "views": views, "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장 →", OUT)


if __name__ == "__main__":
    main()

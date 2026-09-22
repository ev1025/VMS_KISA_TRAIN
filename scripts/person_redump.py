# -*- coding: utf-8 -*-
"""침입·배회용 사람 트랙 덤프 재생성 (타일 검출 + 자체 트래커).

왜 다시 만드는가 (실측):
  기존 덤프는 정답 시각에 박스가 0개인 영상이 여럿이었는데, 같은 프레임을 person_v3 로
  직접 돌려보면 사람이 conf 0.76~0.93 으로 잘 잡힌다. 즉 검출은 되는데 덤프에 안 남았다.
  원인은 ByteTrack 이 새 트랙을 만들 때 요구하는 신뢰도(new_track_thresh)를 원거리 인물이
  간헐적으로만 넘겨서 트랙이 아예 생성되지 않은 것.
  또 원본 한 장 추론은 원거리 인물에 0.39~0.76 으로 불안정한데, 3x3 겹침 타일 + 960 입력이면
  0.79~0.93 으로 안정된다.

그래서: 타일로 검출 → 겹친 박스 합치기(NMS) → 단순 IoU 트래커로 번호 부여 → 기존과 같은 형식으로 저장.
출력 한 줄 = {"t": 초, "boxes": [[트랙번호, 신뢰도, x1, y1, x2, y2], ...]}
"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import kisa_paths as _KP   # 경로는 한 곳에서만 정한다(docs/file_path.md 1절)
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

W = _KP.V.parent
G = W / "vms"


# 검출·추적 코드는 제출 도구에서 가져온다. 복사본을 두면 언제든 갈라진다.
# 실제로 2026-09-16 에 nms 의 contain 기본값이 달라 침입이 94.74 대 87.72 로 갈렸다.
import sys as _sys
_sys.path.insert(0, str(G / "_kisa_port/tools"))
from kisa_items import tiles_of, iou, contained, nms, Tracker, TILE   # noqa: E402,F401


def run(model, mp4, out, stride, grid, overlap, imgsz, conf, contain=0.75):
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * stride))
    trk = Tracker()
    i = 0
    lines = []
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                dets = []
                for crop, ox, oy in tiles_of(fr, grid, overlap):
                    r = model.predict(crop, conf=conf, verbose=False, imgsz=imgsz, classes=[0])[0]
                    for b in r.boxes:
                        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                        dets.append((float(b.conf), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
                boxes = trk.update(nms(dets, contain=contain))
                lines.append(json.dumps({"t": round(i / fps, 2), "boxes": boxes}))
        i += 1
    cap.release()
    out.write_text("\n".join(lines) + "\n")
    return len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--item", required=True, choices=["침입", "배회"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=float, default=0.5)
    ap.add_argument("--grid", type=int, default=3)
    ap.add_argument("--overlap", type=float, default=0.2)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.15)
    # 부분검출 억제 기준. 제출 경로(_kisa_port/tools/kisa_items.py 의 PersonDetector)는
    # process() 에서 contain=None 으로 부르고, 그러면 내부에서 2.0 을 쓴다 = 억제를 끈다.
    # 이 값이 다르면 트랙이 달라져 같은 판정기를 써도 점수가 어긋난다(2026-09-16 실측 87.72 대 94.74).
    ap.add_argument("--contain", type=float, default=0.75,
                    help="부분검출 억제 기준(0.75=켬). 제출 경로와 맞추려면 2.0(끔)")
    ap.add_argument("--videos", default=None,
                    help="영상 폴더. 기본은 채점 견본(deploy_val). 2026-09-20: 연구개발 침입·배회 영상(처음 보는 영상 잣대)에도 쓰기 위해 추가")
    a = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(a.model)
    if a.videos:
        src = Path(a.videos)
    else:
        src = next(p for p in (G / "data/원본데이터/kisa_배포_검증영상/deploy_val").iterdir() if p.name.startswith(a.item))
    vids = sorted(src.rglob("*.mp4"))
    outd = Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    print(f"{a.item} {len(vids)}편 · 격자 {a.grid}x{a.grid} 겹침 {a.overlap} 입력 {a.imgsz} conf {a.conf}", flush=True)
    for n, v in enumerate(vids, 1):
        f = outd / f"{v.stem}.jsonl"
        if f.exists():
            continue
        c = run(model, v, f, a.stride, a.grid, a.overlap, a.imgsz, a.conf, a.contain)
        print(f"  [{n}/{len(vids)}] {v.stem} {c}표본", flush=True)
    print("완료", flush=True)


if __name__ == "__main__":
    main()

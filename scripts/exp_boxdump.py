# -*- coding: utf-8 -*-
"""실험(학습된 모델)별 박스 덤프. 영상 검수 탭에서 모델 예측 박스를 영상 위에 겹쳐 보기 위한 것.

사용: python scripts/exp_boxdump.py <실험명> <클립stem>
출력: dumps/fire_box/<실험명>/<stem>.jsonl — 각 줄 {"t": 초, "boxes": [[cls, conf, x1, y1, x2, y2]]} (픽셀 좌표)

채점(score_kisa)과 같은 0.5초 간격·타일 추론을 써서, 화면에서 보는 박스가 채점 근거와 같게 한다.
모델은 results/<실험명>/meta.json 의 best_pt 를 쓰고, 없으면 runs/<실험명> 아래에서 찾는다.
"""
import json, sys
from pathlib import Path
import cv2
from ultralytics import YOLO

import kisa_paths as KP

V = KP.V
STRIDE_S = KP.SAMPLE_STRIDE_S      # 채점과 같은 표본 간격이어야 시각이 맞는다
CONF = 0.10                        # 낮게 떠 두고 화면 쪽에서 걸러 본다(drawZone 이 0.25 컷)


def best_pt(exp):
    """학습 결과 가중치 경로. meta.json 우선, 없으면 runs/ 탐색."""
    mj = V / "results" / exp / "meta.json"
    if mj.is_file():
        try:
            p = (json.loads(mj.read_text(encoding="utf-8")) or {}).get("best_pt")
            if p and Path(p).is_file():
                return Path(p)
        except Exception:
            pass
    for c in sorted((V / "runs" / exp).rglob("best.pt")):
        return c
    return None


find_mp4 = KP.find_mp4


def model_kind(exp):
    """이 실험이 불 모델인지 사람 모델인지. 큐마다 item 을 방화/사람/침입/배회/쓰러짐 으로
    달리 적어 놔서 방화만 불로 보고 나머지는 사람으로 본다."""
    mj = V / "results" / exp / "meta.json"
    if mj.is_file():
        try:
            item = (json.loads(mj.read_text(encoding="utf-8")) or {}).get("item")
            if item:
                return "fire" if item == "방화" else "person"
        except Exception:
            pass
    return "fire"                      # 예전 실험은 전부 방화였다


def tiles(frame):
    """풀프레임 + 4분할 + 중앙. 작은 불·연기를 놓치지 않으려는 채점과 같은 구성."""
    h, w = frame.shape[:2]
    out = [((0, 0), frame)]
    for x, y in ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4)):
        out.append(((x, y), frame[y:y + h // 2, x:x + w // 2]))
    return out


def views(frame, kind):
    """추론할 조각들. 불은 잘라서 키워 보고, 사람은 화면 그대로 한 번만 본다."""
    return tiles(frame) if kind == "fire" else [((0, 0), frame)]


def dump(exp, stem):
    pt = best_pt(exp)
    if not pt:
        print("가중치 없음:", exp); return 2
    mp4 = find_mp4(stem)
    if not mp4:
        print("영상 없음:", stem); return 2

    outdir = V / "dumps/fire_box" / exp
    outdir.mkdir(parents=True, exist_ok=True)
    kind = model_kind(exp)
    imgsz = 640 if kind == "fire" else 960      # 사람은 풀프레임 한 장이라 조금 키워 본다
    model = YOLO(str(pt))
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * STRIDE_S))

    rows, i = [], 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                boxes = []
                for (ox, oy), sub in views(frame, kind):
                    for res in model.predict(sub, conf=CONF, imgsz=imgsz, verbose=False):
                        for b in res.boxes:
                            x1, y1, x2, y2 = (float(z) for z in b.xyxy[0])
                            boxes.append([int(b.cls[0]), round(float(b.conf[0]), 3),
                                          round(x1 + ox, 1), round(y1 + oy, 1),
                                          round(x2 + ox, 1), round(y2 + oy, 1)])
                rows.append({"t": round(i / fps, 2), "boxes": boxes})
        i += 1
    cap.release()

    tmp = outdir / (stem + ".jsonl.tmp")          # 다 쓰기 전에 읽히지 않게 임시로 쓰고 바꾼다
    tmp.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    tmp.replace(outdir / (stem + ".jsonl"))
    print("완료", exp, stem, len(rows), "표본")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용: exp_boxdump.py <실험명> <클립stem>"); sys.exit(2)
    sys.exit(dump(sys.argv[1], sys.argv[2]))

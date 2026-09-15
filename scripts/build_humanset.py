# -*- coding: utf-8 -*-
"""손라벨(fire_labels.json) → human_fire YOLO 학습셋.
라벨된 프레임을 원본 영상에서 다시 뽑고, 불은 제자리에 머무는 성질을 이용해 ±2초 전파해 표본을 불린다.

- rm 하지 않고 원자적 교체(tmp→replace)로 덮어쓴다: 학습이 human_fire 를 참조 중이어도 안전(torn read 없음).
- val 심링크·data.yaml 은 만들지 않는다(큐 러너가 목록 방식으로 self-val 을 따로 만든다).
- cls < 0 행(검토완료 마커)은 박스로 쓰지 않는다.
실행: python scripts/build_humanset.py   (exp_queue.py --rebuild-human 이 실험 전에 자동 호출)
"""
import cv2, json, os
from collections import defaultdict
from pathlib import Path

import kisa_paths as KP            # 저장소 루트는 여기 한 곳에서만 정의한다
G = KP.V
SRC = G / "data/원본데이터/kisa_연구개발_방화영상"   # src 없는 옛 라벨의 기본 영상 폴더
RAW = G / "data/원본데이터"                          # 라벨에 src(상대경로)가 있으면 이 기준
OUT = G / "data/학습데이터/human_fire"
LABELS = G / "data/학습데이터/손라벨/fire_labels.json"
PROP = [-2.0, -1.0, 0.0, 1.0, 2.0]                   # 전파 오프셋(초)


def atomic_img(path, fr):
    ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        return False
    tmp = str(path) + ".tmp"
    open(tmp, "wb").write(buf.tobytes()); os.replace(tmp, path); return True


def atomic_txt(path, text):
    tmp = str(path) + ".tmp"
    open(tmp, "w").write(text); os.replace(tmp, path)


def main():
    (OUT / "images/train").mkdir(parents=True, exist_ok=True)
    (OUT / "labels/train").mkdir(parents=True, exist_ok=True)
    rows = json.load(open(LABELS, encoding="utf-8"))
    by = defaultdict(list)
    for r in rows:
        by[(r["clip"], r["t"])].append(r)
    n_img = n_box = n_novideo = 0
    for (clip, t), rs in sorted(by.items()):
        src = next((r.get("src") for r in rs if r.get("src")), None)
        mp4 = (RAW / src) if src else SRC / (clip + ".mp4")
        if not mp4.exists():
            n_novideo += 1; continue
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
        for off in PROP:
            tt = t + off
            if tt < 0:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(tt * fps))
            ok, fr = cap.read()
            if not ok:
                continue
            ts = f"{float(t):.2f}".rstrip("0").rstrip(".").replace(".", "p")
            stem = f"{clip}_{ts}_{off:+.0f}".replace("+", "p").replace("-", "m")
            lines = []
            for r in rs:
                if int(r.get("cls", 0)) < 0:               # 검토완료 마커는 박스 아님
                    continue
                cx = r["x"] + r["w"] / 2; cy = r["y"] + r["h"] / 2   # 손라벨 x,y = 좌상단 → 중심 변환
                if not (0 < cx < 1 and 0 < cy < 1):
                    continue
                lines.append(f"{r['cls']} {cx:.6f} {cy:.6f} {r['w']:.6f} {r['h']:.6f}"); n_box += 1
            if atomic_img(OUT / "images/train" / (stem + ".jpg"), fr):
                atomic_txt(OUT / "labels/train" / (stem + ".txt"), "\n".join(lines)); n_img += 1
        cap.release()
    total = sum(1 for _ in (OUT / "images/train").glob("*.jpg"))
    print(f"human_fire 재빌드: 이미지 {n_img} · 박스 {n_box} · 소스영상없음 {n_novideo} · 폴더 총 {total}장")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""덤프를 만든 가중치가 지금도 그 값을 내는가.

계기(2026-09-16)
    앙상블을 붙였는데 라이브가 오프라인과 어긋났다. 원인은 규칙이 아니라 가중치였다.
    runs/s2_s960_20260913 이 09-15 재학습 실패로 덮어써져서, 좋은 덤프(09-14)를 만든 모델이
    3에폭짜리 실패본으로 바뀌어 있었다. 덤프만 보고 모델을 고르면 이런 일이 난다.

쓰는 법
    python scripts/fire_weight_check.py <실험이름> <가중치.pt> [해상도]
"""
import json
import sys
from pathlib import Path
import cv2
V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import kisa_paths as KP   # noqa: E402
from ultralytics import YOLO   # noqa: E402

NAMES = {0: "fire", 1: "smoke"}
tag = sys.argv[1]
wpt = sys.argv[2]
z = int(sys.argv[3]) if len(sys.argv) > 3 else 640
d = json.loads((V / "dumps/score_tl" / f"{tag}.json").read_text())
m = YOLO(wpt)
print(f"덤프 {tag} · 가중치 {wpt} · 해상도 {z}")

bad = 0; n = 0
for stem in sorted(d):
    rows = {round(r[0], 1): (r[1], r[2]) for r in d[stem]["rows"]}
    mp = next(KP.videos("방화").rglob(f"{stem}.mp4"), None)
    if mp is None:
        continue
    cap = cv2.VideoCapture(str(mp))
    # 그 편에서 불 신뢰도가 가장 높았던 표본 3개만 다시 재 본다
    top = sorted(rows.items(), key=lambda kv: -kv[1][0])[:3]
    for t, (kf, ks) in top:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, fr = cap.read()
        if not ok:
            continue
        h, w = fr.shape[:2]
        crops = [fr] + [fr[y:y + h // 2, x:x + w // 2] for x, y in
                        ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
        f = 0.0
        for c in crops:
            for b in m.predict(c, conf=0.05, imgsz=z, verbose=False)[0].boxes:
                if NAMES.get(int(b.cls)) == "fire":
                    f = max(f, float(b.conf))
        n += 1
        ok2 = abs(f - kf) <= 0.02
        bad += 0 if ok2 else 1
        print(f"  {stem} t={t:7.1f}  덤프 {kf:.3f}  지금 {f:.3f}  {'같음' if ok2 else '다름'}")
    cap.release()
print(f"\n{n}개 표본 중 어긋남 {bad}개 -> " + ("가중치가 덤프와 맞는다" if bad == 0 else "이 덤프는 이 가중치가 만든 것이 아니다"))
sys.exit(1 if bad else 0)

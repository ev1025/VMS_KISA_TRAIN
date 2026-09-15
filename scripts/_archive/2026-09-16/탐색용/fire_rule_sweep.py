# -*- coding: utf-8 -*-
"""화재 규칙 재설계 스윕 (학습 없이). base 타일 원시 conf 를 GT 대조.
   272(fire0.82 미검) 원인 + smoke 게이트로 195/216(연기만) 회수 시도.
   덤프: 전 영상 0.5s 6뷰 타일 (fire,smoke) → 규칙 그리드. 비화재 20편으로 오탐 체크."""
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
import cv2
from ultralytics import YOLO

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W / "vms"
DELAY, BEFORE, AFTER = 10.0, 2.0, 10.0


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(x):
    if not x.exists(): return None
    al = ET.parse(x).getroot().find(".//Alarm"); return hms(al.findtext("StartTime")) if al is not None else None


def tiles(fr):
    h, w = fr.shape[:2]
    return [fr] + [fr[y:y+h//2, x:x+w//2] for x, y in ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4))]


def dump(model, mp4):
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps*0.5)); i = 0; rows = []
    while True:
        if not cap.grab(): break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                bf = bs = 0.0
                for c in tiles(fr):
                    r = model.predict(c, conf=0.05, verbose=False, imgsz=640)[0]
                    for b in r.boxes:
                        if int(b.cls) == 0: bf = max(bf, float(b.conf))
                        else: bs = max(bs, float(b.conf))
                rows.append((round(i/fps, 2), bf, bs))
        i += 1
    cap.release(); return rows


def onset(rows, fth, sth, win, hits, smoke_on):
    q = deque(maxlen=win)
    for t, bf, bs in rows:
        hit = bf >= fth or (smoke_on and bs >= sth)
        q.append((t, hit))
        if sum(h for _, h in q) >= hits:
            return next(t0 for t0, h in q if h)
    return None


def main():
    m = YOLO(str(G/"model/fire_base.pt"))
    pos = [(mp4, gt_start(W/"vms/data/원본데이터/kisa_배포_방화채점셋/gt"/(mp4.stem+".xml"))) for mp4 in sorted((W/"vms/data/원본데이터/kisa_배포_방화채점셋/videos").glob("*.mp4"))]
    neg = [(mp4, None) for mp4 in sorted((G/"datasets/rnd_rest/5. 싸움(200개)").rglob("*.mp4"))[:20]]
    data = [(mp4, gt, dump(m, mp4)) for mp4, gt in pos + neg]
    print("덤프 완료", len(data))

    best = None
    for fth in (0.35, 0.4, 0.45, 0.5):
        for sth in (0.6, 0.7, 0.8):
            for win, hits in ((6,4),(6,3),(8,4),(4,2)):
                for smoke_on in (False, True):
                    tp=fn=fp=0
                    for mp4, gt, rows in data:
                        on = onset(rows, fth, sth, win, hits, smoke_on)
                        sa = None if on is None else on+DELAY
                        if gt is None:
                            fp += 0 if sa is None else 1
                        elif sa is not None and gt-BEFORE <= sa <= gt+AFTER:
                            tp += 1
                        else:
                            fn += 1
                            if sa is not None: fp += 1
                    r = tp/(tp+fn) if tp+fn else 0; p = tp/(tp+fp) if tp+fp else 0
                    f1 = 2*r*p/(r+p)*100 if r+p else 0
                    key = (f1, -fp)
                    if best is None or key > best[0]:
                        best = (key, dict(fire=fth, smoke=sth, win=win, hits=hits, smoke_on=smoke_on, tp=tp, fn=fn, fp=fp, f1=round(f1,1)))
    print("최적:", best[1])
    # 272 단독 진단: fire 0.82 인데 왜 미검이었나 (기존 규칙 fth0.4 win6 hits4)
    for mp4, gt, rows in data:
        if "272" in mp4.stem:
            hi = [(t, bf) for t, bf, bs in rows if bf >= 0.4]
            print(f"272: GT {gt}, fire>=0.4 인 시각들 {hi[:8]}, onset(기존규칙)={onset(rows,0.4,0.6,6,4,False)}")


if __name__ == "__main__":
    main()

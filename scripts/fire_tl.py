# -*- coding: utf-8 -*-
"""방화 10편 타임라인: 0.5s 6뷰 타일 → 프레임별 max fire/smoke conf. CPU. → fire_tl.json"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import kisa_paths as _KP   # 경로는 한 곳에서만 정한다(docs/file_path.md 1절)
import json, xml.etree.ElementTree as ET
from pathlib import Path
import cv2
from ultralytics import YOLO

W = _KP.V.parent; G = _KP.V


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt(x):
    if not x.exists(): return None, None
    r = ET.parse(x).getroot(); al = r.find(".//Alarm")
    dur = r.findtext(".//Duration")
    return (hms(al.findtext("StartTime")) if al is not None else None), dur


def tiles(fr):
    h, w = fr.shape[:2]
    return [fr] + [fr[y:y+h//2, x:x+w//2] for x, y in ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4))]


m = YOLO(str(G/"model/fire_base.pt"))
out = {}
for mp4 in sorted((W/"vms/data/원본데이터/kisa_배포_방화채점셋/videos").glob("*.mp4")):
    g, dur = gt(W/"vms/data/원본데이터/kisa_배포_방화채점셋/gt"/(mp4.stem+".xml"))
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    step = max(1, round(fps*0.5)); i = 0; sig = []
    while True:
        if not cap.grab(): break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                bf = bs = 0.0
                for c in tiles(fr):
                    r = m.predict(c, conf=0.05, verbose=False, imgsz=640)[0]
                    for b in r.boxes:
                        if int(b.cls) == 0: bf = max(bf, float(b.conf))
                        else: bs = max(bs, float(b.conf))
                sig.append([round(i/fps, 1), round(bf, 3), round(bs, 3)])
        i += 1
    cap.release()
    out[mp4.stem] = {"duration": round(total, 1), "gt_start": g, "fire_smoke": sig}
    print(mp4.stem, len(sig), flush=True)

json.dump(out, open(G/"fire_tl.json", "w"))
print("saved fire_tl.json")

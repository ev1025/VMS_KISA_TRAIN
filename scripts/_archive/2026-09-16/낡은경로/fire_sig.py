# -*- coding: utf-8 -*-
"""방화 신호열 추출: 연구개발 75편(양성) + 비화재 60편(음성) → 0.5초마다 6뷰 타일 max fire/smoke conf.
   온셋 분류기 학습용. GPU 사용."""
import json, sys, xml.etree.ElementTree as ET
from pathlib import Path
import cv2
from ultralytics import YOLO

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W / "vms"


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600 + int(m)*60 + int(s)


def gt_start(x):
    if not x.exists(): return None
    al = ET.parse(x).getroot().find(".//Alarm")
    return hms(al.findtext("StartTime")) if al is not None else None


def tiles(fr):
    h, w = fr.shape[:2]
    return [fr] + [fr[y:y+h//2, x:x+w//2] for x, y in ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4))]


def sig(model, mp4, cap_sec=None):
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
                rows.append([round(i/fps,1), round(bf,3), round(bs,3)])
        i += 1
        if cap_sec and i/fps > cap_sec: break
    cap.release(); return rows


def main():
    m = YOLO(str(G/"model/fire_base.pt"))
    out = {}
    pos = sorted((G/"data/원본데이터/kisa_연구개발_방화영상").glob("*.mp4"))
    for k, mp4 in enumerate(pos, 1):
        gt = gt_start(mp4.with_suffix(".xml"))
        out[mp4.stem] = {"gt": gt, "sig": sig(m, mp4), "label": "fire"}
        print(f"[pos {k}/{len(pos)}] {mp4.stem} gt={gt}", flush=True)
    # 음성: 비화재에서 60편 (각 카테고리 20편, 앞 3분만)
    neg = []
    for d in sorted((G/"data/rnd/rnd_rest").glob("*")):
        neg += sorted(d.rglob("*.mp4"))[:20]
    for k, mp4 in enumerate(neg, 1):
        out["NEG_"+mp4.stem] = {"gt": None, "sig": sig(m, mp4, cap_sec=180), "label": "neg"}
        print(f"[neg {k}/{len(neg)}] {mp4.stem}", flush=True)
    json.dump(out, open(G/"fire_sig_train.json", "w"))
    print("saved fire_sig_train.json", len(out))


if __name__ == "__main__":
    main()

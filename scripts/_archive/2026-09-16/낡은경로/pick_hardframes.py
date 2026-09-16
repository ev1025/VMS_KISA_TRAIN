# -*- coding: utf-8 -*-
"""방화 손라벨용 하드 프레임 선별. 라벨링 효과가 가장 큰 프레임부터 뽑는다.

효과 큰 프레임 = 모델이 헷갈리는 것:
  - 불이 있을 법한데 신뢰도가 애매(0.15~0.5)한 프레임 → 라벨하면 결정경계를 또렷하게
  - 미라벨 클립 → 아예 없던 장면
  - 이미 확신(>0.7)하거나 확실히 없는(<0.1) 프레임은 라벨 효과 적음 → 제외
클립당 상한을 둬서 다양성 확보(한 클립에 몰리지 않게).
"""
import json, glob, os, sys
from pathlib import Path
import cv2, numpy as np

GY = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/vms")
SRC = GY/"data/원본데이터/kisa_연구개발_방화영상"
OUT = GY/"data/학습데이터/손라벨/new"          # 새 손라벨 프레임 폴더
MODEL = GY/"runs/par/human_full/yolo11s/weights/best.pt"
STRIDE = 1.0                       # 초당 1프레임 스캔
PER_CLIP = 6                       # 클립당 최대 프레임
LOW, HIGH = 0.15, 0.55            # 이 신뢰도 구간 = 애매 = 라벨 가치 높음

def tiles(fr):
    h, w = fr.shape[:2]
    return [fr] + [fr[y:y+h//2, x:x+w//2] for x,y in ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4))]

def main():
    from ultralytics import YOLO
    m = YOLO(str(MODEL))
    labeled = set(r["clip"] for r in json.load(open(GY/"data/학습데이터/손라벨/fire_labels.json")))
    OUT.mkdir(exist_ok=True)
    picks = []
    vids = sorted(SRC.glob("*.mp4"))
    for vi, v in enumerate(vids, 1):
        clip = v.stem
        unl = clip not in labeled       # 미라벨 클립은 가산점
        cap = cv2.VideoCapture(str(v)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps*STRIDE)); i = 0
        cand = []
        while True:
            if not cap.grab(): break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    best_f = best_s = 0.0
                    for c in tiles(fr):
                        r = m.predict(c, conf=0.05, verbose=False, imgsz=640)[0]
                        for b in r.boxes:
                            cf = float(b.conf); cls = int(b.cls)
                            if cls == 0: best_f = max(best_f, cf)
                            else: best_s = max(best_s, cf)
                    peak = max(best_f, best_s)
                    # 애매 구간 점수 (0.35 근처가 최고)
                    if LOW <= peak <= HIGH or (unl and peak >= 0.1):
                        score = 1.0 - abs(peak - 0.35)/0.35 + (0.5 if unl else 0)
                        cand.append((score, round(i/fps,1), fr.copy(), round(best_f,2), round(best_s,2)))
            i += 1
        cap.release()
        cand.sort(key=lambda x:-x[0])
        for rank,(sc,t,fr,bf,bs) in enumerate(cand[:PER_CLIP]):
            name = f"{clip}_{int(t):04d}.png"
            cv2.imwrite(str(OUT/name), fr)
            picks.append({"file":name,"clip":clip,"t":t,"W":fr.shape[1],"H":fr.shape[0],
                          "fire":bf,"smoke":bs,"unlabeled":unl,"score":round(sc,2)})
        if vi % 10 == 0: print(f"  {vi}/{len(vids)} · 누적 {len(picks)}장", flush=True)
    picks.sort(key=lambda x:-x["score"])
    json.dump(picks, open(OUT/"meta.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n선별 {len(picks)}장 → {OUT}")
    print(f"  미라벨 클립분: {sum(1 for p in picks if p['unlabeled'])}장")
    print(f"  애매(0.15~0.55): {sum(1 for p in picks if 0.15<=max(p['fire'],p['smoke'])<=0.55)}장")

if __name__ == "__main__":
    main()

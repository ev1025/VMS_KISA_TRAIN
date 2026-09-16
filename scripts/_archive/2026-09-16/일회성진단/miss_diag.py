# -*- coding: utf-8 -*-
"""화재 미검 5편 진짜 원인 진단: GT창 프레임에서 base 모델이 무엇을 보나.
   불이 작은가/먼가/연기만인가/장면유형. + FASDD 원시 통계."""
import json, glob, random, xml.etree.ElementTree as ET
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W / "vms"
MISS = ["C00_012_0007", "C00_155_0003", "C00_195_0001", "C00_216_0003", "C00_272_0003"]
HIT = ["C00_038_0006", "C00_049_0001", "C00_146_0003"]


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(x):
    al = ET.parse(x).getroot().find(".//Alarm"); return hms(al.findtext("StartTime")) if al is not None else None


def tiles(fr):
    h, w = fr.shape[:2]
    return [("full", fr)] + [(n, fr[y:y+h//2, x:x+w//2]) for n, (x, y) in
            zip("q1 q2 q3 q4 ctr".split(), ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4)))]


def diag(model, mp4, gt):
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps*0.5)); i = 0
    best_f = best_s = 0.0; best_view = ""; best_area = 0; hot = 0; nfr = 0
    while True:
        if not cap.grab(): break
        t = i/fps
        if i % step == 0 and gt-2 <= t <= gt+10:
            ok, fr = cap.retrieve()
            if ok:
                nfr += 1
                g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
                hot = max(hot, float((g > 230).mean())*100)      # 초고휘도(불꽃 코어) 화소%
                for vn, c in tiles(fr):
                    r = model.predict(c, conf=0.03, verbose=False, imgsz=640)[0]
                    for b in r.boxes:
                        cf = float(b.conf); cls = int(b.cls)
                        x1,y1,x2,y2 = b.xyxy[0]
                        area = float((x2-x1)*(y2-y1))/(c.shape[0]*c.shape[1])
                        if cls == 0 and cf > best_f:
                            best_f, best_view, best_area = cf, vn, area
                        if cls == 1: best_s = max(best_s, cf)
        if t > gt+10: break
        i += 1
    cap.release()
    return dict(fire=round(best_f,2), smoke=round(best_s,2), view=best_view,
               fire면적=round(best_area,4), 초고휘도최대=round(hot,3), 프레임=nfr)


def main():
    m = YOLO(str(G/"model/fire_base.pt"))
    print("=== 미검 5편: GT창에서 base 가 보는 것 ===")
    for s in MISS:
        gt = gt_start(W/"vms/data/원본데이터/kisa_배포_방화채점셋/gt"/(s+".xml"))
        print(f"  {s} (GT {gt}s): {diag(m, W/'vms/data/원본데이터/kisa_배포_방화채점셋/videos'/(s+'.mp4'), gt)}")
    print("=== 정검 3편 대조 ===")
    for s in HIT:
        gt = gt_start(W/"vms/data/원본데이터/kisa_배포_방화채점셋/gt"/(s+".xml"))
        print(f"  {s} (GT {gt}s): {diag(m, W/'vms/data/원본데이터/kisa_배포_방화채점셋/videos'/(s+'.mp4'), gt)}")

    # FASDD 원시 박스크기·밝기
    print("\n=== FASDD 원시 통계 (박스 크기·밝기) ===")
    F = G/"datasets/ext/fasdd"
    d = json.load(open(F/"annotations/train.json"))
    imgs = {im["id"]: im for im in d["images"]}
    fire_sz, smoke_sz = [], []
    for a in d["annotations"]:
        im = imgs[a["image_id"]]; area = (a["bbox"][2]*a["bbox"][3])/(im["width"]*im["height"])
        (fire_sz if a["category_id"] == 0 else smoke_sz).append(area)
    print(f"  fire 박스 면적 중앙값 {np.median(fire_sz):.4f} · 소형(<0.01) {np.mean(np.array(fire_sz)<0.01)*100:.0f}%")
    print(f"  smoke 박스 면적 중앙값 {np.median(smoke_sz):.4f}")
    # 밝기 표본
    random.seed(0); samp = random.sample(d["images"], 300); br = []
    for im in samp:
        p = list(F.glob(f"images/*/{Path(im['file_name']).name}"))
        if p:
            g = cv2.imread(str(p[0]), cv2.IMREAD_GRAYSCALE)
            if g is not None: br.append(g.mean())
    br = np.array(br)
    print(f"  밝기: 야간<60 {(br<60).mean()*100:.0f}% · 황혼 {((br>=60)&(br<=110)).mean()*100:.0f}% · 주간>110 {(br>110).mean()*100:.0f}% · 평균 {br.mean():.0f}")


if __name__ == "__main__":
    main()

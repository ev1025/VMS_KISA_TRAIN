# -*- coding: utf-8 -*-
"""방화 배포 10편 fire/smoke 박스 dump (영상 검수 오버레이용).
   신호/알람과 일치시키려 신호와 같은 모델(human_full)·타일 추론 사용.
   출력 dumps/fire_box/<stem>.jsonl, 각 줄 {t, boxes:[[cls,conf,x1,y1,x2,y2 픽셀]]}."""
import json, cv2
from pathlib import Path
from ultralytics import YOLO

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
OUT = V/"dumps/fire_box"; OUT.mkdir(parents=True, exist_ok=True)
m = YOLO(str(V/"runs/par/human_full/yolo11s/weights/best.pt"))   # 신호와 동일 모델
CONF = 0.10
import kisa_paths as KP
vids = sorted(KP.videos("방화").glob("*.mp4"))

def tiles(fr):
    h, w = fr.shape[:2]
    out = [((0, 0), fr)]                                   # 풀프레임
    for x, y in ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4)):
        out.append(((x, y), fr[y:y+h//2, x:x+w//2]))      # 4분할 + 중앙
    return out

print("대상", len(vids), "편 · 모델 human_full · 타일", flush=True)
for mp4 in vids:
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps*0.5)); i = 0; recs = []
    while True:
        if not cap.grab(): break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                boxes = []
                for (ox, oy), c in tiles(fr):
                    r = m.predict(c, conf=CONF, imgsz=640, verbose=False)[0]
                    for b in r.boxes:
                        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                        boxes.append([int(b.cls), round(float(b.conf), 3),
                                      round(x1+ox), round(y1+oy), round(x2+ox), round(y2+oy)])
                recs.append({"t": round(i/fps, 1), "boxes": boxes})
        i += 1
    cap.release()
    (OUT/(mp4.stem+".jsonl")).write_text("\n".join(json.dumps(r) for r in recs))
    print("done", mp4.stem, len(recs), "프레임", flush=True)
print("ALL DONE")

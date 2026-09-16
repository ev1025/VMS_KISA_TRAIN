# -*- coding: utf-8 -*-
"""방화 위치 포함 덤프: 낮은 임계(0.05)로 fire/smoke 박스를 좌표까지 저장.
   시공간 누적 규칙용. 배포 10편 + 연구개발 75편(양성) + 비화재 40편(음성)."""
import json, xml.etree.ElementTree as ET
from pathlib import Path
import cv2
from ultralytics import YOLO

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W/"vms"
CONF = 0.05


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600+int(m)*60+int(s)
def gt_start(x):
    if not x.exists(): return None
    al = ET.parse(x).getroot().find(".//Alarm")
    return hms(al.findtext("StartTime")) if al is not None else None
def tiles(fr):
    h, w = fr.shape[:2]
    # (오프셋, 크롭) - 좌표를 원본 기준으로 되돌리기 위해 오프셋 보관
    out = [((0, 0), fr)]
    for x, y in ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4)):
        out.append(((x, y), fr[y:y+h//2, x:x+w//2]))
    return out


def dump(model, mp4, cap_sec=None):
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps*0.5)); i = 0; rows = []
    while True:
        if not cap.grab(): break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                H, Wd = fr.shape[:2]; boxes = []
                for (ox, oy), c in tiles(fr):
                    r = model.predict(c, conf=CONF, verbose=False, imgsz=640)[0]
                    for b in r.boxes:
                        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                        boxes.append([int(b.cls), round(float(b.conf), 3),
                                      round((x1+ox)/Wd, 4), round((y1+oy)/H, 4),
                                      round((x2+ox)/Wd, 4), round((y2+oy)/H, 4)])
                rows.append({"t": round(i/fps, 1), "b": boxes})
        i += 1
        if cap_sec and i/fps > cap_sec: break
    cap.release(); return rows


def main():
    m = YOLO(str(G/"model/fire_base.pt"))
    out = {}
    # 배포 10편 (채점 대상)
    for mp4 in sorted((W/"vms/data/원본데이터/kisa_배포_방화채점셋/videos").glob("*.mp4")):
        gt = gt_start(W/"vms/data/원본데이터/kisa_배포_방화채점셋/gt"/(mp4.stem+".xml"))
        out["DEP_"+mp4.stem] = {"gt": gt, "rows": dump(m, mp4), "split": "deploy"}
        print("dep", mp4.stem, flush=True)
    # 연구개발 75편 (규칙 튜닝용)
    for mp4 in sorted((G/"data/원본데이터/kisa_연구개발_방화영상").glob("*.mp4")):
        gt = gt_start(mp4.with_suffix(".xml"))
        out["TRN_"+mp4.stem] = {"gt": gt, "rows": dump(m, mp4), "split": "train"}
        print("trn", mp4.stem, flush=True)
    # 비화재 음성 40편
    neg = []
    for d in sorted((G/"data/rnd/rnd_rest").glob("*")):
        neg += sorted(d.rglob("*.mp4"))[:14]
    for mp4 in neg[:40]:
        out["NEG_"+mp4.stem] = {"gt": None, "rows": dump(m, mp4, cap_sec=180), "split": "neg"}
        print("neg", mp4.stem, flush=True)
    json.dump(out, open(G/"fire_boxdump.json", "w"))
    print("saved", len(out))


if __name__ == "__main__":
    main()

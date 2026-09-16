# -*- coding: utf-8 -*-
"""못 맞힌 편이 '검출 실패' 인지 '판정 실패' 인지 가른다.

앞 판의 실수
    GT+2 프레임 한 장만 보고 conf 0 이면 '사람을 못 본다' 고 했다.
    창 전체를 보니 같은 편에서 0.8 대가 나왔다. 한 장으로 판단하면 안 된다.

여기서는 항목의 제출 경로 그대로(침입=3x3 타일, 배회=전체프레임 640) 돌리고
구역 안(제출 도구의 entered) 검출만 센다. GT 창 [GT-2, GT+10] 에서
  구역 안 검출이 몇 초나 잡히는가 = 판정이 요구하는 체류를 채울 수 있는가
"""
import sys, xml.etree.ElementTree as ET
from pathlib import Path
import cv2
V = Path(__file__).resolve().parents[1]
for s in ("scripts", "_kisa_port/tools", "_kisa_port"):
    sys.path.insert(0, str(V / s))
import kisa_paths as KP, kisa_items as K
from ultralytics import YOLO   # noqa: E402

det_i = K.PersonDetector(K.WEIGHTS / K.ITEMS["intrusion"]["model"], contain=None)
m_l = YOLO(str(K.WEIGHTS / K.ITEMS["loitering"]["model"]))

CASES = [("C00_249_0003", "침입", "intrusion"), ("C00_255_0001", "침입", "intrusion"),
         ("C00_275_0001", "침입", "intrusion"),
         ("C00_225_0001", "배회", "loitering"), ("C00_115_0001", "배회", "loitering"),
         ("C00_005_0001", "침입", "intrusion"), ("C00_001_0001", "배회", "loitering")]

for stem, item, key in CASES:
    gt = None
    for p in KP.videos(item).rglob(f"{stem}.xml"):
        al = ET.parse(p).getroot().find(".//Alarm")
        if al is None:
            continue
        h, mm, s = (int(v) for v in al.findtext("StartTime").split(":"))
        gt = h * 3600 + mm * 60 + s
    mp = next(KP.videos(item).rglob(f"{stem}.mp4"), None)
    if gt is None or mp is None:
        print(f"{stem}: 영상/GT 없음"); continue
    cfg = K.ITEMS[key]
    cap = cv2.VideoCapture(str(mp))
    ok0, im0 = cap.read()
    wh = (im0.shape[1], im0.shape[0]) if ok0 else None
    poly = K.zone_of(KP.ZONE_MAPS, stem, cfg["zone"], wh)
    hits, tot, best = 0, 0, 0.0
    times = []
    t = gt - 15.0
    while t <= gt + 20.0:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, im = cap.read()
        if not ok:
            t += 0.5; continue
        if key == "intrusion":
            dets = [(c, x1, y1, x2, y2) for c, x1, y1, x2, y2 in det_i.detect(im)]
        else:
            r = m_l.predict(im, conf=0.05, imgsz=cfg["track_imgsz"], classes=[0], verbose=False)[0]
            dets = [(float(b.conf), *(float(v) for v in b.xyxy[0])) for b in r.boxes]
        inz = [c for c, x1, y1, x2, y2 in dets
               if c >= cfg["conf"] and K.entered((x1, y1, x2, y2), poly, cfg["corners"])]
        tot += 1
        if inz:
            hits += 1; times.append(round(t, 1)); best = max(best, max(inz))
        t += 0.5
    cap.release()
    need = cfg.get("dwell", cfg.get("hold", 0))
    print(f"{stem} ({item}) GT={gt} 구역={'전체화면' if poly is None else '있음'}")
    print(f"   구역 안 검출 {hits}/{tot} 표본 · 최고 conf {best:.3f} · 필요 체류 {need}")
    if times:
        print(f"   잡힌 시각 {times[0]}~{times[-1]} : {times[:24]}")
    else:
        print("   구역 안에서 한 번도 안 잡힘")

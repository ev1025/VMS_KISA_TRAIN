# -*- coding: utf-8 -*-
"""라벨링용 전체 프레임 (자동 발화점 탐지 없음). 원본 그대로, 사람이 보고 판단.

프레임은 GT 시각 기준으로 고른다(gt-7 / gt / gt+8). 그래서 GT 가 틀리면 불 없는 장면만 뽑힌다.
실제로 C0501/0502/0503_004 세 편이 그랬다(XML 292초인데 불은 221초 발화 265초 소화).
원본 XML 은 고치지 않고 data/학습데이터/정답라벨/_gt_정정.json 을 먼저 본다.
"""
import cv2, json, xml.etree.ElementTree as ET
from pathlib import Path
G = Path(__file__).resolve().parents[1]
SRC = G/"data/원본데이터/kisa_연구개발_방화영상"; OUT = G/"data/학습데이터/손라벨/full"; OUT.mkdir(exist_ok=True)
FIX = G/"data/학습데이터/정답라벨/_gt_정정.json"
fix = {k: v["start"] for k, v in json.load(open(FIX, encoding="utf-8")).items()
       if isinstance(v, dict) and "start" in v} if FIX.exists() else {}
if fix:
    print("GT 정정 적용:", fix, flush=True)
def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600+int(m)*60+int(s)
meta = []
clips = sorted(SRC.glob("*.mp4"))
for n, mp4 in enumerate(clips, 1):
    x = mp4.with_suffix(".xml")
    if not x.exists(): continue
    al = ET.parse(x).getroot().find(".//Alarm")
    if al is None: continue
    gt = fix.get(mp4.stem, hms(al.findtext("StartTime"))); ign = max(0, gt-10)
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    for tag, tt in (("a", ign+3), ("b", gt), ("c", gt+8)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(tt*fps)))
        ok, fr = cap.read()
        if not ok: continue
        H, W = fr.shape[:2]
        cv2.imwrite(str(OUT/f"{mp4.stem}_{tag}.png"), fr)
        meta.append({"file": f"{mp4.stem}_{tag}.png", "clip": mp4.stem, "t": round(tt,1), "gt": gt,
                     "W": W, "H": H, "x0": 0, "y0": 0, "cw": W, "ch": H, "auto": False})
    cap.release()
    if n % 20 == 0: print(f"[{n}/{len(clips)}]", flush=True)
json.dump(meta, open(OUT/"meta.json","w"), ensure_ascii=False)
print("전체프레임", len(meta), "장")

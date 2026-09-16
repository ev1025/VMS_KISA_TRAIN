import cv2, json, xml.etree.ElementTree as ET
from pathlib import Path
G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
SRC = G/"data/원본데이터/kisa_연구개발_방화영상"; OUT = G/"labels/set"; OUT.mkdir(exist_ok=True)
def hms(t):
    h,m,s=(t or "0:0:0").split(":"); return int(h)*3600+int(m)*60+int(s)
meta = []
for mp4 in sorted(SRC.glob("*.mp4")):
    x = mp4.with_suffix(".xml")
    if not x.exists(): continue
    al = ET.parse(x).getroot().find(".//Alarm")
    if al is None: continue
    gt = hms(al.findtext("StartTime"))          # 점화+10초
    ign = max(0, gt-10)                          # 점화 추정
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    for tag, tt in (("a", ign+3), ("b", gt), ("c", gt+8)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(tt*fps)); ok, fr = cap.read()
        if not ok: continue
        h, w = fr.shape[:2]
        name = f"{mp4.stem}_{tag}.jpg"
        cv2.imwrite(str(OUT/name), fr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        meta.append({"file": name, "clip": mp4.stem, "t": round(tt,1), "gt": gt, "w": w, "h": h})
    cap.release()
json.dump(meta, open(OUT/"meta.json","w"), ensure_ascii=False)
print("프레임", len(meta), "장 →", OUT)

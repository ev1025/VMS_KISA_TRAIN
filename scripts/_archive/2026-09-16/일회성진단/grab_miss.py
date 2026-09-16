import cv2, xml.etree.ElementTree as ET
from pathlib import Path
W = Path("/NHNHOME/WORKSPACE/26mss002_E3")
out = W/"vms"/"results"/"missframes"; out.mkdir(exist_ok=True)
MISS = ["C00_012_0007","C00_155_0003","C00_195_0001","C00_216_0003","C00_272_0003"]
def hms(t):
    h,m,s=(t or "0:0:0").split(":"); return int(h)*3600+int(m)*60+int(s)
for s in MISS:
    x = W/"vms/data/원본데이터/kisa_배포_방화채점셋/gt"/(s+".xml")
    al = ET.parse(x).getroot().find(".//Alarm")
    gt = hms(al.findtext("StartTime"))
    cap = cv2.VideoCapture(str(W/"vms/data/원본데이터/kisa_배포_방화채점셋/videos"/(s+".mp4")))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    # GT 시점(=점화+10초) 과 점화 추정 시점(GT-10) 두 장
    for tag, tt in (("gt", gt), ("ign", max(0, gt-10))):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(tt*fps)); ok, fr = cap.read()
        if ok:
            fr = cv2.resize(fr, (960, 540))
            cv2.imwrite(str(out/f"{s}_{tag}.jpg"), fr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    cap.release(); print(s, "gt", gt)
print("saved", out)

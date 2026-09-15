"""침입 미검 클립: GT 주변 프레임에 구역 다각형(노란)과 원본 덤프 박스(녹=3꼭짓점 구역내, 적=아님)를 그려 2x2 몽타주로 저장."""
import json, sys, os, xml.etree.ElementTree as ET, cv2, numpy as np
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools"); import kisa_items as K
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"; D = f"{V}/data/원본데이터/kisa_배포_검증영상"
VID = f"{D}/deploy_val/침입(30개)/배포"; DUMP = f"{V}/dumps/_archive/intrusion_tile_predup"; OUT = f"{V}/results/kisa_port/viz_miss"
os.makedirs(OUT, exist_ok=True)
def gt(stem):
    r = ET.parse(f"{VID}/{stem}.xml").getroot().find(".//Alarm"); h, m, s = r.findtext("StartTime").split(":"); return int(h)*3600+int(m)*60+int(s)
for stem in sys.argv[1:]:
    g = gt(stem); poly = K.zone_of(f"{D}/zone_maps", stem, "Intrusion")
    rows = {round(json.loads(l)["t"], 1): json.loads(l)["boxes"] for l in open(f"{DUMP}/{stem}.jsonl")}
    cap = cv2.VideoCapture(f"{VID}/{stem}.mp4"); fps = cap.get(cv2.CAP_PROP_FPS)
    tiles = []
    for t in (g - 6, g - 3, g, g + 3):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps))); ok, fr = cap.read()
        if not ok: continue
        cv2.polylines(fr, [np.array(poly, np.int32)], True, (0, 255, 255), 2)
        # 덤프는 0.5초 격자 → 가장 가까운 표본
        key = min(rows, key=lambda k: abs(k - t))
        for pid, conf, x1, y1, x2, y2 in rows[key]:
            ok3 = K.entered((x1, y1, x2, y2), poly, 3); okf = K.entered((x1, y1, x2, y2), poly, 0)
            col = (0, 255, 0) if ok3 else ((255, 160, 0) if okf else (0, 0, 255))
            cv2.rectangle(fr, (int(x1), int(y1)), (int(x2), int(y2)), col, 2)
            cv2.putText(fr, f"{pid}:{conf:.2f}", (int(x1), max(12, int(y1) - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
        cv2.putText(fr, f"{stem} t={t}s (gt={g})  box@{key}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        tiles.append(cv2.resize(fr, (960, 540)))
    while len(tiles) < 4: tiles.append(np.zeros_like(tiles[0]))
    m = np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])])
    cv2.imwrite(f"{OUT}/{stem}.jpg", m, [cv2.IMWRITE_JPEG_QUALITY, 80]); print("saved", stem)

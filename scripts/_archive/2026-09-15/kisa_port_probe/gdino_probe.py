"""Grounding DINO 를 우리 실패 클립에 돌려 '사람이 보이기는 하는가'만 본다.
비교 대상 = 같은 프레임의 현행 person YOLO. 정상 클립을 대조군으로 함께 넣는다."""
import os, sys, json, torch, cv2, numpy as np, xml.etree.ElementTree as ET
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools"); import kisa_items as K
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"; D = f"{V}/data/원본데이터/kisa_배포_검증영상"
OUT = f"{V}/dumps/kisa_port/gdino"; os.makedirs(OUT, exist_ok=True)
MID = "IDEA-Research/grounding-dino-base"
PROMPT = "a person. a pedestrian. a human. a man walking. a person with an umbrella."
CLIPS = [                                                    # (항목, 폴더, stem, 설명)
    ("intrusion", "침입(30개)", "C00_126_0002", "우천 주간 우산 · 미검"),
    ("intrusion", "침입(30개)", "C00_249_0003", "설경 주간 울타리뒤 · 미검"),
    ("intrusion", "침입(30개)", "C00_255_0001", "야간 IR 눈 · 미검"),
    ("intrusion", "침입(30개)", "C00_275_0001", "야간 설경 원거리 · 미검"),
    ("loitering", "배회(30개)", "C00_115_0001", "배회 · 박스 0개"),
    ("loitering", "배회(30개)", "C00_225_0001", "배회 · 박스 0개"),
    ("intrusion", "침입(30개)", "C00_005_0001", "대조군(정검)"),
]
dev = "cuda" if torch.cuda.is_available() else "cpu"
proc = AutoProcessor.from_pretrained(MID)
gd = AutoModelForZeroShotObjectDetection.from_pretrained(MID).to(dev).eval()
yolo = K.PersonDetector(K.WEIGHTS / "person_v3.pt", contain=None)          # 침입과 같은 타일 검출
print(f"모델 로드 완료 ({dev})\n", flush=True)

def gt_of(folder, stem):
    r = ET.parse(f"{D}/deploy_val/{folder}/배포/{stem}.xml").getroot().find(".//Alarm")
    h, m, s = r.findtext("StartTime").split(":"); return int(h)*3600+int(m)*60+int(s)

rows = []
for item, folder, stem, note in CLIPS:
    g = gt_of(folder, stem)
    cap = cv2.VideoCapture(f"{D}/deploy_val/{folder}/배포/{stem}.mp4"); fps = cap.get(cv2.CAP_PROP_FPS)
    tiles = []; n_gd = n_yolo = 0; best_gd = best_yolo = 0.0
    for t in (g - 4, g - 2, g, g + 2, g + 4):                              # GT 앞뒤 5프레임만
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps))); ok, fr = cap.read()
        if not ok: continue
        rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
        with torch.no_grad():
            inp = proc(images=rgb, text=PROMPT, return_tensors="pt").to(dev)
            o = gd(**inp)
            r = proc.post_process_grounded_object_detection(
                o, inp.input_ids, threshold=0.20, text_threshold=0.20,
                target_sizes=[rgb.shape[:2]])[0]
        gdb = [(float(s), *[float(v) for v in b]) for s, b in zip(r["scores"], r["boxes"])]
        yb = yolo.detect(fr)
        n_gd += len(gdb); n_yolo += len(yb)
        best_gd = max([best_gd] + [b[0] for b in gdb]); best_yolo = max([best_yolo] + [b[0] for b in yb])
        vis = fr.copy()
        for s, x1, y1, x2, y2 in gdb:
            cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(vis, f"GD {s:.2f}", (int(x1), max(12, int(y1)-4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
        for s, x1, y1, x2, y2 in yb:
            cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
            cv2.putText(vis, f"Y {s:.2f}", (int(x1), int(y2)+14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)
        cv2.putText(vis, f"{stem} t={t} (gt={g})", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        tiles.append(cv2.resize(vis, (640, 360)))
    if tiles:
        while len(tiles) % 3: tiles.append(np.zeros_like(tiles[0]))
        rws = [np.hstack(tiles[i:i+3]) for i in range(0, len(tiles), 3)]
        cv2.imwrite(f"{OUT}/{stem}.jpg", np.vstack(rws), [cv2.IMWRITE_JPEG_QUALITY, 82])
    rows.append((stem, note, n_gd, best_gd, n_yolo, best_yolo))
    print(f"  {stem} {note:22s} GDINO 박스 {n_gd:3d}(최고 {best_gd:.2f}) · 현행YOLO {n_yolo:3d}(최고 {best_yolo:.2f})", flush=True)
print("\n=== 요약 (GT 앞뒤 5프레임) ===")
print(f"{'클립':16s} {'상황':24s} {'GDINO':>12s} {'현행YOLO':>12s}")
for stem, note, ng, bg, ny, by in rows:
    print(f"{stem:16s} {note:24s} {ng:4d}/{bg:.2f} {ny:8d}/{by:.2f}")

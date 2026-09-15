"""GDINO 오탐률: 학습영상(채점셋 아님) 야간 클립에서 이벤트 한참 전(사람 없을 구간) 프레임을 뽑아
GDINO 가 헛박스를 뱉는지 센다. NMS 적용 후 세어 중복은 제거한다."""
import os, sys, glob, torch, cv2, numpy as np, xml.etree.ElementTree as ET
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools"); import kisa_items as K
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"; SRC = f"{V}/data/원본데이터/kisa_연구개발_사람영상"
OUT = f"{V}/dumps/kisa_port/gdino_fp"; os.makedirs(OUT, exist_ok=True)
PROMPT = "a person. a pedestrian. a human. a man walking. a person with an umbrella."
dev = "cuda"; MID = "IDEA-Research/grounding-dino-base"
proc = AutoProcessor.from_pretrained(MID); gd = AutoModelForZeroShotObjectDetection.from_pretrained(MID).to(dev).eval()

def night_clips(sub, n):
    out = []
    for x in sorted(glob.glob(f"{SRC}/{sub}/*.xml")):
        r = ET.parse(x).getroot()
        if (r.findtext(".//TimeOfDay") or "").strip().lower() != "night": continue
        a = r.find(".//Alarm")
        if a is None or not a.findtext("StartTime"): continue
        h, m, s = a.findtext("StartTime").split(":")
        out.append((x[:-4] + ".mp4", int(h)*3600+int(m)*60+int(s)))
        if len(out) >= n: break
    return out

def detect(fr, th):
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = proc(images=rgb, text=PROMPT, return_tensors="pt").to(dev)
        r = proc.post_process_grounded_object_detection(gd(**inp), inp.input_ids, threshold=th,
                                                        text_threshold=th, target_sizes=[rgb.shape[:2]])[0]
    dets = [(float(s), *[float(v) for v in b]) for s, b in zip(r["scores"], r["boxes"])]
    return K.nms(dets, contain=2.0)                       # 겹침 NMS 만(우리 침입과 동일)

clips = night_clips("2. 침입(170개)", 6) + night_clips("1. 배회(325개)", 6)
print(f"야간 학습클립 {len(clips)}편 · 이벤트 90초 이전 구간(사람 없을 것으로 기대)\n", flush=True)
for th in (0.25, 0.30, 0.35, 0.40):
    tot = n_box = 0; worst = []
    for mp4, g in clips:
        cap = cv2.VideoCapture(mp4); fps = cap.get(cv2.CAP_PROP_FPS)
        for t in (10, 25, 40, 55, 70):
            if t > g - 90: continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps))); ok, fr = cap.read()
            if not ok: continue
            d = detect(fr, th); tot += 1; n_box += len(d)
            if d: worst.append((len(d), max(x[0] for x in d), os.path.basename(mp4), t))
    worst.sort(reverse=True)
    print(f"  th {th:.2f}: {tot}프레임 중 헛박스 {n_box}개 (프레임당 {n_box/max(tot,1):.2f})  최악 {worst[:3]}", flush=True)

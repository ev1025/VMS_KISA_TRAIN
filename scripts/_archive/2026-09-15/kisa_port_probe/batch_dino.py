"""학습영상 495편(침입170·배회325)의 이벤트 전후 구간을 DINO 로 미리 훑어 자동라벨을 저장한다.
대시보드 '자동라벨' 탭은 이 결과를 그냥 읽어 띄운다(그때그때 돌리지 않는다).

- 야간 클립부터 처리한다. person_v3 가 가장 못 보는 구간이고 손라벨 예산을 여기 쓸 것이라서.
- 임계 0.25: 빈 프레임 60장에서 헛박스 1개. 사람이 검수하는 전제라 놓치는 것보다 낫다.
- 클립 단위로 저장하고 이미 있으면 건너뛴다(중단해도 이어서 돌릴 수 있다).
"""
import os, sys, json, glob, time, argparse, xml.etree.ElementTree as ET
import torch, cv2

sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools")
import kisa_items as K
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
SRC = f"{V}/data/원본데이터/kisa_연구개발_사람영상"
OUT = f"{V}/data/학습데이터/자동라벨/dino"
PROMPT = "a person. a pedestrian. a human. a man walking. a person with an umbrella."
SUBS = {"intrusion": "2. 침입(170개)", "loitering": "1. 배회(325개)"}

ap = argparse.ArgumentParser()
ap.add_argument("--span", type=float, default=20.0)     # 정답 시각 앞뒤 초
ap.add_argument("--step", type=float, default=0.5)      # 라벨 간격(사람 항목 2FPS)
ap.add_argument("--th", type=float, default=0.25)
ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()
os.makedirs(OUT, exist_ok=True)

dev = "cuda" if torch.cuda.is_available() else "cpu"
proc = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-base")
gd = AutoModelForZeroShotObjectDetection.from_pretrained("IDEA-Research/grounding-dino-base").to(dev).eval()
print(f"DINO 로드 ({dev}) · 임계 {a.th} · 앞뒤 {a.span}초 · 간격 {a.step}초", flush=True)


def _iou(p, q):
    ix1 = max(p[0], q[0]); iy1 = max(p[1], q[1]); ix2 = min(p[2], q[2]); iy2 = min(p[3], q[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (p[2]-p[0])*(p[3]-p[1]) + (q[2]-q[0])*(q[3]-q[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _cmax(p, q):
    """두 박스 중 작은 쪽이 상대 안에 들어간 비율(양방향).
    DINO 는 같은 사람에 '상반신'과 '전신' 같은 박스를 같이 내는데 IoU 로는 안 걸린다."""
    ix1 = max(p[0], q[0]); iy1 = max(p[1], q[1]); ix2 = min(p[2], q[2]); iy2 = min(p[3], q[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    sp = (p[2]-p[0])*(p[3]-p[1]); sq = (q[2]-q[0])*(q[3]-q[1])
    return max(inter / sp if sp > 0 else 0.0, inter / sq if sq > 0 else 0.0)


def detect(fr):
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = proc(images=rgb, text=PROMPT, return_tensors="pt").to(dev)
        r = proc.post_process_grounded_object_detection(gd(**inp), inp.input_ids, threshold=a.th,
                                                         text_threshold=a.th, target_sizes=[rgb.shape[:2]])[0]
    d = sorted([(float(s), *[float(v) for v in b]) for s, b in zip(r["scores"], r["boxes"])],
               key=lambda x: -x[0])
    keep = []
    for x in d:
        if all(_iou(x[1:], k[1:]) < 0.4 and _cmax(x[1:], k[1:]) < 0.9 for k in keep):
            keep.append(x)
    h0, w0 = fr.shape[:2]
    return [[0, round(x1/w0, 5), round(y1/h0, 5), round((x2-x1)/w0, 5), round((y2-y1)/h0, 5), round(sc, 3)]
            for sc, x1, y1, x2, y2 in keep]


jobs = []                                  # (야간우선, 항목, xml, mp4, gt)
for item, sub in SUBS.items():
    for x in sorted(glob.glob(f"{SRC}/{sub}/*.xml")):
        try:
            r = ET.parse(x).getroot()
        except Exception:
            continue
        al = r.find(".//Alarm")
        if al is None or not al.findtext("StartTime"):
            continue
        h, m, s = al.findtext("StartTime").split(":")
        night = (r.findtext(".//TimeOfDay") or "").strip().lower() == "night"
        jobs.append((0 if night else 1, item, x, x[:-4] + ".mp4", int(h)*3600+int(m)*60+int(s), night))
jobs.sort(key=lambda j: (j[0], j[2]))       # 야간 먼저
if a.limit:
    jobs = jobs[:a.limit]
n_night = sum(1 for j in jobs if j[5])
print(f"대상 {len(jobs)}편 (야간 {n_night}편 먼저)", flush=True)

t0 = time.time(); n_done = 0
for i, (_, item, xml, mp4, gt, night) in enumerate(jobs, 1):
    stem = os.path.basename(xml)[:-4]
    dst = f"{OUT}/{stem}.json"
    if os.path.exists(dst):
        continue
    if not os.path.exists(mp4):
        continue
    cap = cv2.VideoCapture(mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    frames = {}
    t = max(0.0, gt - a.span)
    while t <= min(dur, gt + a.span) + 1e-6:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(t * fps)), 0))
        ok, fr = cap.read()
        if ok:
            frames[f"{t:.1f}"] = detect(fr)
        t = round(t + a.step, 2)
    cap.release()
    tmp = dst + ".tmp"
    json.dump({"clip": stem, "item": item, "night": night, "gt": gt, "th": a.th, "step": a.step,
               "W": W, "H": H, "model": "grounding-dino-base", "frames": frames},
              open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, dst)
    n_done += 1
    hit = sum(1 for v in frames.values() if v)
    el = time.time() - t0
    print(f"  [{i}/{len(jobs)}] {stem} {'야간' if night else '주간'} {len(frames)}프레임 · 사람 잡힘 {hit} "
          f"({el/60:.0f}분 경과, 편당 {el/max(n_done,1):.0f}초)", flush=True)
print(f"완료: 새로 처리 {n_done}편 → {OUT}", flush=True)

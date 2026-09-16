# -*- coding: utf-8 -*-
"""사람라벨 기반 합성증강: 라벨된 불 패치를 같은 도메인의 다른 배경(정상 구간)에 합성.
   기존 실패한 합성(안개 오버레이·외부 산불)과 다른 점:
     - 붙이는 불이 '우리 도메인 실제 불'(사람라벨)
     - 붙이는 배경도 '같은 촬영 체계의 정상 프레임'
   → 도메인 이동 없이 위치·배경 다양성만 늘린다."""
import cv2, json, numpy as np, random, xml.etree.ElementTree as ET
from pathlib import Path

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
SRC = G/"data/원본데이터/kisa_연구개발_방화영상"
OUT = G/"data/학습데이터/human_synth"
N_PER_BG = 2          # 배경 1장당 합성 수
random.seed(0)

for s in ("images/train", "labels/train"):
    (OUT/s).mkdir(parents=True, exist_ok=True)


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600+int(m)*60+int(s)


rows = json.load(open(G/"data/학습데이터/손라벨/fire_labels.json", encoding="utf-8"))
fire_rows = [r for r in rows if r["cls"] == 0]
print("불 라벨:", len(fire_rows))

# 1) 불 패치 추출 (원본 프레임에서 크롭)
patches = []
by_frame = {}
for r in fire_rows:
    by_frame.setdefault((r["clip"], r["t"]), []).append(r)
for (clip, t), rs in by_frame.items():
    mp4 = SRC/(clip+".mp4")
    if not mp4.exists(): continue
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t*fps)); ok, fr = cap.read(); cap.release()
    if not ok: continue
    H, W = fr.shape[:2]
    for r in rs:
        x1, y1 = int(r["x"]*W), int(r["y"]*H)
        x2, y2 = int((r["x"]+r["w"])*W), int((r["y"]+r["h"])*H)
        if x2-x1 < 6 or y2-y1 < 6: continue
        patches.append(fr[y1:y2, x1:x2].copy())
print("추출 패치:", len(patches))

# 2) 배경: 각 클립의 정상 구간(점화 한참 전)
bgs = []
for mp4 in sorted(SRC.glob("*.mp4")):
    x = mp4.with_suffix(".xml")
    if not x.exists(): continue
    al = ET.parse(x).getroot().find(".//Alarm")
    if al is None: continue
    gt = hms(al.findtext("StartTime"))
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    for off in (60, 40):
        tt = gt - off
        if tt < 2: continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(tt*fps)); ok, fr = cap.read()
        if ok: bgs.append((mp4.stem, int(tt), fr))
    cap.release()
print("배경:", len(bgs))

# 3) 합성 (알파 블렌딩 + 밝기 매칭)
n = 0
for stem, tt, bg in bgs:
    H, W = bg.shape[:2]
    for k in range(N_PER_BG):
        img = bg.copy(); lines = []
        for _ in range(random.randint(1, 2)):
            p = random.choice(patches)
            sc = random.uniform(0.7, 1.6)
            ph, pw = max(6, int(p.shape[0]*sc)), max(6, int(p.shape[1]*sc))
            if ph >= H//3 or pw >= W//3: continue
            pr = cv2.resize(p, (pw, ph), interpolation=cv2.INTER_LINEAR)
            # 지면 근처 랜덤 배치
            px = random.randint(0, W-pw-1); py = random.randint(int(H*0.35), H-ph-1)
            # 불은 밝은 부분만 남기는 소프트 마스크
            g = cv2.cvtColor(pr, cv2.COLOR_BGR2GRAY).astype(np.float32)
            m = np.clip((g - g.mean())/(g.std()+1e-6), 0, 3)/3.0
            m = cv2.GaussianBlur(m, (5, 5), 0)[..., None]
            roi = img[py:py+ph, px:px+pw].astype(np.float32)
            img[py:py+ph, px:px+pw] = (roi*(1-m) + pr.astype(np.float32)*m).astype(np.uint8)
            cx, cy = (px+pw/2)/W, (py+ph/2)/H
            lines.append(f"0 {cx:.6f} {cy:.6f} {pw/W:.6f} {ph/H:.6f}")
        if not lines: continue
        name = f"syn_{stem}_{tt}_{k}"
        cv2.imwrite(str(OUT/"images/train"/(name+".jpg")), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (OUT/"labels/train"/(name+".txt")).write_text("\n".join(lines))
        n += 1
print("합성 생성:", n)

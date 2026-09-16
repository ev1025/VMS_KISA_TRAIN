# -*- coding: utf-8 -*-
"""라벨링 크롭: 발화점 = '깜빡임(temporal std) 이 크고 + 기준보다 밝은' 영역.
   불은 시시각각 흔들린다. 주차된 차·건물은 흔들리지 않으므로 배제된다."""
import cv2, json, numpy as np, xml.etree.ElementTree as ET
from pathlib import Path

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
SRC = G/"data/원본데이터/kisa_연구개발_방화영상"; OUT = G/"labels/crop"; OUT.mkdir(exist_ok=True)
CROP = 512

def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600+int(m)*60+int(s)

def grab(cap, fps, t):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t*fps)))
    ok, fr = cap.read()
    return fr if ok else None

def burst(cap, fps, t0, n=24, step_f=3):
    """t0 부터 연속 프레임 n장 (깜빡임 측정용)"""
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t0*fps)))
    out = []
    for i in range(n*step_f):
        ok, fr = cap.read()
        if not ok: break
        if i % step_f == 0:
            out.append(cv2.GaussianBlur(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (7,7), 0).astype(np.float32))
    return out

def focus(ref, frames):
    """깜빡임(시간축 표준편차) × 밝아짐 → 최대 지점"""
    if len(frames) < 6:
        return None
    stack = np.stack(frames)                      # (T,H,W)
    flick = stack.std(axis=0)                      # 깜빡임
    mean = stack.mean(axis=0)
    refg = cv2.GaussianBlur(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), (7,7), 0).astype(np.float32)
    up = np.clip(mean - refg, 0, None)            # 기준보다 밝아진 정도
    score = flick * (1.0 + up/32.0)               # 깜빡임 위주, 밝아짐 가중
    score = cv2.GaussianBlur(score, (15,15), 0)
    _, mx, _, loc = cv2.minMaxLoc(score)
    if mx < 3.0:                                   # 깜빡임 신호 너무 약함
        return None
    return int(loc[0]), int(loc[1])

meta = []
clips = sorted(SRC.glob("*.mp4"))
for n, mp4 in enumerate(clips, 1):
    x = mp4.with_suffix(".xml")
    if not x.exists(): continue
    al = ET.parse(x).getroot().find(".//Alarm")
    if al is None: continue
    gt = hms(al.findtext("StartTime")); ign = max(0, gt-10)
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    ref = grab(cap, fps, max(0, ign-20))
    if ref is None: cap.release(); continue
    H, W = ref.shape[:2]
    fr_burst = burst(cap, fps, gt+6)               # 불이 자란 시점에서 깜빡임 측정
    c = focus(ref, fr_burst)
    cx, cy = c if c else (W//2, H//2)
    x0 = max(0, min(W-CROP, cx-CROP//2)); y0 = max(0, min(H-CROP, cy-CROP//2))
    cw = min(CROP, W-x0); ch = min(CROP, H-y0)
    for tag, tt in (("a", ign+3), ("b", gt), ("c", gt+8)):
        fr = grab(cap, fps, tt)
        if fr is None: continue
        big = cv2.resize(fr[y0:y0+ch, x0:x0+cw], (cw*2, ch*2), interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(str(OUT/f"{mp4.stem}_{tag}.jpg"), big, [cv2.IMWRITE_JPEG_QUALITY, 90])
        meta.append({"file": f"{mp4.stem}_{tag}.jpg", "clip": mp4.stem, "t": round(tt,1), "gt": gt,
                     "W": W, "H": H, "x0": x0, "y0": y0, "cw": cw, "ch": ch, "auto": bool(c)})
    cap.release()
    if n % 15 == 0: print(f"[{n}/{len(clips)}]", flush=True)
json.dump(meta, open(OUT/"meta.json","w"), ensure_ascii=False)
print("크롭", len(meta), "· 깜빡임탐지", sum(1 for m in meta if m["auto"]))

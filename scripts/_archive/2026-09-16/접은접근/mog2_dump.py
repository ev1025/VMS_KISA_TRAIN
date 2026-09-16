# -*- coding: utf-8 -*-
"""MOG2 배경차분 실측 (제미나이 '모션 안전망' 주장 검증, CPU).
  intrusion 모드: 침입 배포 30편 → 사람 크기 전경 블롭을 탐지박스(conf 1.0, id -1)로 jsonl 덤프
                  → 로컬 intrusion_sweep 으로 구역 채점 (탐지 0.00 인 7편 회수 여부)
  fire 모드     : KISA 화재 10편 GT창 vs 사전구간, 비화재 20편의 전경비율·플리커 최대값 비교"""
import json, sys, xml.etree.ElementTree as ET
from pathlib import Path
import cv2, numpy as np

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W / "vms"
STRIDE = 0.5


def mog():
    return cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=False)


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(xml):
    al = ET.parse(xml).getroot().find(".//Alarm")
    return hms(al.findtext("StartTime")) if al is not None else None


def intrusion(out):
    out.mkdir(parents=True, exist_ok=True)
    vids = sorted((G / "datasets/deploy_val/침입(30개)/배포").glob("*.mp4"))
    k = np.ones((5, 5), np.uint8)
    for i, mp4 in enumerate(vids, 1):
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps * STRIDE)); bg = mog(); n = 0
        with open(out / (mp4.stem + ".jsonl"), "w") as f:
            while True:
                ok, fr = cap.read()
                if not ok: break
                fg = bg.apply(fr)
                if n % step == 0 and n > fps * 2:              # 배경 안정화 2초 후
                    fg = cv2.morphologyEx(cv2.morphologyEx(fg, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
                    boxes = []
                    for c in cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
                        x, y, w, h = cv2.boundingRect(c)
                        if h >= 40 and 1.2 <= h / max(w, 1) <= 5.0 and w * h >= 800:   # 직립 사람 크기
                            boxes.append([-1, 1.0, x, y, x + w, y + h])
                    f.write(json.dumps({"t": round(n / fps, 2), "boxes": boxes}) + "\n")
                n += 1
        cap.release(); print(f"[{i}/{len(vids)}] {mp4.stem}", flush=True)


def fire_stats(mp4, gt=None):
    """0.5초마다 (전경비율, 전경 내 프레임차 플리커). 반환: GT창 최대, 사전구간 최대, 전체 최대"""
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * STRIDE)); bg = mog(); prev = None; n = 0; rows = []
    while True:
        ok, fr = cap.read()
        if not ok: break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY); fg = bg.apply(fr)
        if n % step == 0 and n > fps * 2 and prev is not None:
            m = fg > 0
            ratio = float(m.mean())
            flick = float(np.abs(g.astype(np.int16) - prev.astype(np.int16))[m].mean()) if m.any() else 0.0
            rows.append((n / fps, ratio, flick))
        prev = g; n += 1
        if gt is not None and n / fps > gt + 10: break
    cap.release()
    def mx(sel):
        s = [(r, f) for t, r, f in rows if sel(t)]
        return (max(r for r, _ in s), max(f for _, f in s)) if s else (0.0, 0.0)
    if gt is None:
        return mx(lambda t: True)
    return mx(lambda t: gt - 2 <= t <= gt + 10), mx(lambda t: t < gt - 5)


def fire():
    print(f"{'화재영상':16s} {'GT창 fg%':>9s} {'GT창 플리커':>10s} {'사전 fg%':>9s} {'사전 플리커':>10s}")
    for mp4 in sorted((W / "vms/data/원본데이터/kisa_배포_방화채점셋/videos").glob("*.mp4")):
        gt = gt_start(W / "vms/data/원본데이터/kisa_배포_방화채점셋/gt" / (mp4.stem + ".xml"))
        (r1, f1), (r0, f0) = fire_stats(mp4, gt)
        print(f"{mp4.stem:16s} {r1*100:9.2f} {f1:10.1f} {r0*100:9.2f} {f0:10.1f}", flush=True)
    print(f"\n{'비화재(싸움) 영상':16s} {'전체 fg%':>9s} {'전체 플리커':>10s}")
    neg = sorted((G / "datasets/rnd_rest/5. 싸움(200개)").rglob("*.mp4"))[:20]
    for mp4 in neg:
        r, f = fire_stats(mp4)
        print(f"{mp4.stem:16s} {r*100:9.2f} {f:10.1f}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "intrusion":
        intrusion(G / "dumps/intrusion_mog2")
    else:
        fire()

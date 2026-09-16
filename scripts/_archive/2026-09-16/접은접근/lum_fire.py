# -*- coding: utf-8 -*-
"""화재 '고휘도 클러스터 팽창' 규칙 실측 (의견: IR 에서 불 = 포화 화소 덩어리가 커지는 속도).
   0.5초마다: 고휘도 마스크(gray > 프레임 평균+3σ, 최소 200) 최대 연결성분 면적(%) → 1초 팽창률.
   화재 10편: GT창 최대 vs 사전구간 최대. 음성: 비화재(싸움) 20편 전체 최대. 겹치면 규칙 불가."""
import xml.etree.ElementTree as ET
from pathlib import Path
import cv2, numpy as np

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W / "vms"


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(xml):
    al = ET.parse(xml).getroot().find(".//Alarm")
    return hms(al.findtext("StartTime")) if al is not None else None


def series(mp4, tmax=None):
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps * 0.5)); n = 0; rows = []
    while True:
        ok, fr = cap.read()
        if not ok: break
        if n % step == 0:
            g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            thr = max(200, g.mean() + 3 * g.std())
            m = (g > thr).astype(np.uint8)
            cnt, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
            area = stats[1:, cv2.CC_STAT_AREA].max() / g.size * 100 if cnt > 1 else 0.0
            rows.append((n / fps, area, float(g.mean())))
        n += 1
        if tmax and n / fps > tmax: break
    cap.release()
    # 1초(2표본) 팽창률
    exp = [(rows[i][0], rows[i][1] - rows[i - 2][1]) for i in range(2, len(rows))]
    return rows, exp


def mx(seq, sel, idx):
    v = [r[idx] for r in seq if sel(r[0])]
    return max(v) if v else 0.0


print(f"{'화재':16s} {'밝기':>5s} | {'GT창 면적%':>9s} {'GT창 팽창':>9s} | {'사전 면적%':>9s} {'사전 팽창':>9s}")
for mp4 in sorted((W / "vms/data/원본데이터/kisa_배포_방화채점셋/videos").glob("*.mp4")):
    gt = gt_start(W / "vms/data/원본데이터/kisa_배포_방화채점셋/gt" / (mp4.stem + ".xml"))
    rows, exp = series(mp4, gt + 10)
    inwin = lambda t: gt - 2 <= t <= gt + 10; pre = lambda t: t < gt - 5
    print(f"{mp4.stem:16s} {np.mean([r[2] for r in rows]):5.0f} | {mx(rows, inwin, 1):9.2f} {mx(exp, inwin, 1):9.2f} | "
          f"{mx(rows, pre, 1):9.2f} {mx(exp, pre, 1):9.2f}", flush=True)
print(f"\n{'비화재(싸움)':16s} {'밝기':>5s} | {'전체 면적%':>9s} {'전체 팽창':>9s}")
for mp4 in sorted((G / "datasets/rnd_rest/5. 싸움(200개)").rglob("*.mp4"))[:20]:
    rows, exp = series(mp4)
    print(f"{mp4.stem:16s} {np.mean([r[2] for r in rows]):5.0f} | {mx(rows, lambda t: True, 1):9.2f} {mx(exp, lambda t: True, 1):9.2f}", flush=True)

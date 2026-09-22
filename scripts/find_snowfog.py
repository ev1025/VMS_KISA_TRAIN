# -*- coding: utf-8 -*-
"""연구개발 방화 영상에서 설경·안개 장면을 찾아 손라벨용 프레임으로 뽑아낸다.

왜: 배포 10편 중 못 잡는 2편이 설경(눈밭 위 작은 불꽃)과 짙은 안개인데,
    24k 메타에는 날씨 태그가 없어(주간/야간만 있음) 화면 통계로 직접 찾아야 한다.
판별(HSV 통계, 프레임을 여러 장 뽑아 평균):
  설경 = 밝고(V 높음) 색이 옅고(S 낮음) 아주 밝은 화소 비율이 큼
  안개 = 밝은데 명암 대비가 낮음(V 표준편차 작음) + 채도 낮음
찾은 영상은 화재 시각 주변 프레임을 손라벨 폴더에 저장한다.
"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import kisa_paths as _KP   # 경로는 한 곳에서만 정한다(docs/file_path.md 1절)
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

W = _KP.V.parent
G = W / "vms"


def stats(mp4, n=9):
    cap = cv2.VideoCapture(str(mp4))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        cap.release(); return None
    vs, ss, stds, brights = [], [], [], []
    for k in range(1, n + 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * k / (n + 1)))
        ok, fr = cap.read()
        if not ok:
            continue
        hsv = cv2.cvtColor(cv2.resize(fr, (320, 180)), cv2.COLOR_BGR2HSV)
        v = hsv[:, :, 2].astype(np.float32)
        s = hsv[:, :, 1].astype(np.float32)
        vs.append(v.mean()); ss.append(s.mean()); stds.append(v.std())
        brights.append(float((v > 200).mean()))
    cap.release()
    if not vs:
        return None
    return dict(V=float(np.mean(vs)), S=float(np.mean(ss)),
                std=float(np.mean(stds)), bright=float(np.mean(brights)))


def classify(st):
    """반환: (분류, 점수). 점수가 클수록 그 성질이 강함."""
    snow = (st["bright"] * 2.0) + max(0.0, (140 - st["S"]) / 140) + max(0.0, (st["V"] - 120) / 135)
    fog = max(0.0, (70 - st["std"]) / 70) * 2.0 + max(0.0, (110 - st["S"]) / 110) + max(0.0, (st["V"] - 100) / 155)
    if st["bright"] >= 0.18 and st["S"] <= 90:
        return "설경후보", snow
    if st["std"] <= 42 and st["S"] <= 80 and st["V"] >= 110:
        return "안개후보", fog
    return "보통", max(snow, fog)


def gt_of(mp4):
    for c in (mp4.parent, G / "lf_gt/fire", W / "vms/data/원본데이터/kisa_배포_방화채점셋/gt"):
        p = c / (mp4.stem + ".xml")
        if p.exists():
            a = ET.parse(p).getroot().find(".//Alarm")
            if a is not None:
                h, m, s = a.findtext("StartTime").split(":")
                return int(h) * 3600 + int(m) * 60 + int(s)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(G / "data/원본데이터/kisa_연구개발_방화영상"))
    ap.add_argument("--out", default=str(G / "labels/snowfog"))
    ap.add_argument("--per", type=int, default=6, help="영상당 뽑을 프레임 수")
    ap.add_argument("--extract", action="store_true", help="후보 영상의 프레임을 실제로 저장")
    a = ap.parse_args()
    src = Path(a.src)
    vids = sorted(src.rglob("*.mp4"))
    print(f"영상 {len(vids)}편 스캔", flush=True)
    rows = []
    for i, v in enumerate(vids, 1):
        st = stats(v)
        if st is None:
            continue
        cls, sc = classify(st)
        rows.append((sc, cls, v, st))
        if i % 20 == 0:
            print(f"  {i}/{len(vids)}", flush=True)
    rows.sort(key=lambda r: -r[0])
    print(f"\n{'영상':26s} {'분류':8s} {'점수':>6} {'밝기V':>6} {'채도S':>6} {'대비std':>7} {'밝은화소':>8}")
    for sc, cls, v, st in rows:
        if cls != "보통" or sc > 1.2:
            print(f"  {v.stem:24s} {cls:8s} {sc:6.2f} {st['V']:6.1f} {st['S']:6.1f} {st['std']:7.1f} {st['bright']:8.2f}")
    cand = [r for r in rows if r[1] != "보통"]
    print(f"\n후보 {len(cand)}편 / 전체 {len(rows)}편")

    if a.extract and cand:
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        meta = {}
        for sc, cls, v, st in cand:
            g = gt_of(v)
            cap = cv2.VideoCapture(str(v)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if g is not None:
                # 화재 시각 전후를 촘촘히 (불이 커지는 과정을 담아야 작은 불을 라벨할 수 있음)
                times = [g - 4, g, g + 4, g + 10, g + 20, g + 35][:a.per]
            else:
                times = [total / fps * k / (a.per + 1) for k in range(1, a.per + 1)]
            for t in times:
                if t < 0 or t * fps >= total:
                    continue
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
                ok, fr = cap.read()
                if not ok:
                    continue
                name = f"{v.stem}_{int(t):04d}.png"
                cv2.imwrite(str(out / name), fr)
                meta[name] = {"clip": v.stem, "t": round(float(t), 1), "gt": g,
                              "kind": cls, "W": fr.shape[1], "H": fr.shape[0]}
            cap.release()
        json.dump(meta, open(out / "meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"프레임 {len(meta)}장 저장 → {out}")


if __name__ == "__main__":
    main()

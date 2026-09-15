# -*- coding: utf-8 -*-
"""방화 채점 상세판: 영상별 판정 + 신호 시계열 저장 + 넓은 규칙 스윕.

기존 score_kisa.py 는 합계 F1 만 출력하고 덤프를 버려서, 어떤 영상을 왜 놓쳤는지 알 수 없었다.
이 스크립트는 (1) 영상별 GT/알람/판정, (2) 정답 시각 부근 최대 신뢰도, (3) 신호 시계열 JSON 을 남긴다.
한 번 저장해두면 규칙 스윕은 추론 없이 즉시 반복할 수 있다.
사용: fire_detail.py <가중치.pt> --tag 이름 [--tiles] [--imgsz 640]
"""
import argparse
import json
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import cv2

W = Path("/NHNHOME/WORKSPACE/26mss002_E3")
G = W / "vms"
VID = W / "vms/data/원본데이터/kisa_배포_방화채점셋/videos"
GT = W / "vms/data/원본데이터/kisa_배포_방화채점셋/gt"
OUTDIR = G / "dumps/score_tl"
DELAY, BEFORE, AFTER = 10.0, 2.0, 10.0
NAMES = {0: "fire", 1: "smoke"}


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(x):
    r = ET.parse(x).getroot().find(".//Alarm")
    return hms(r.findtext("StartTime")) if r is not None else None


def dump(model, mp4, stride, tiles, imgsz):
    """(시각, fire 최대신뢰도, smoke 최대신뢰도) 목록. 타일 = 원본 + 4분할 + 중앙."""
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * stride))
    i, rows = 0, []
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                bf = bs = 0.0
                crops = [fr]
                if tiles:
                    h, w = fr.shape[:2]
                    crops += [fr[y:y + h // 2, x:x + w // 2] for x, y in
                              ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
                for c in crops:
                    r = model.predict(c, conf=0.03, verbose=False, imgsz=imgsz)[0]
                    for b in r.boxes:
                        cls = NAMES.get(int(b.cls), "?")
                        cf = float(b.conf)
                        if cls == "fire":
                            bf = max(bf, cf)
                        elif cls == "smoke":
                            bs = max(bs, cf)
                rows.append((round(i / fps, 2), round(bf, 4), round(bs, 4)))
        i += 1
    cap.release()
    return rows


def onset(rows, kind, fire, smoke, window, hits):
    win = deque(maxlen=window)
    for t, bf, bs in rows:
        if kind == "fire_only":
            hit = bf >= fire
        elif kind == "combined":
            hit = bf >= fire or (bf >= 0.3 and bs >= smoke)
        elif kind == "smoke_ok":            # 연기 단독으로도 발화 인정(스펙상 연기도 정식 이벤트)
            hit = bf >= fire or bs >= smoke
        else:
            hit = bf >= fire or bs >= fire
        win.append((t, hit))
        if sum(1 for _, h in win if h) >= hits:
            return next(t0 for t0, h in win if h)
    return None


def verdict(gt, sa):
    if sa is None:
        return "미검"
    return "정검" if gt - BEFORE <= sa <= gt + AFTER else "오검"


def score(per, kind, fire, smoke, window, hits):
    tp = fn = fp = 0
    det = []
    for stem, (rows, gt) in per.items():
        o = onset(rows, kind, fire, smoke, window, hits)
        sa = None if o is None else o + DELAY
        v = verdict(gt, sa)
        if v == "정검":
            tp += 1
        elif v == "미검":
            fn += 1
        else:
            fp += 1
            fn += 1
        det.append((stem, gt, sa, v))
    r = tp / (tp + fn) if tp + fn else 0
    p = tp / (tp + fp) if tp + fp else 0
    return (round(2 * r * p / (r + p) * 100, 2) if r + p else 0.0), tp, fn, fp, det


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--stride", type=float, default=0.5)
    ap.add_argument("--reuse", action="store_true", help="저장된 시계열이 있으면 추론 생략")
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    tl = OUTDIR / f"{a.tag}.json"

    if a.reuse and tl.exists():
        raw = json.load(open(tl))
        per = {k: ([tuple(x) for x in v["rows"]], v["gt"]) for k, v in raw.items()}
        print(f"저장된 시계열 재사용: {tl}", flush=True)
    else:
        from ultralytics import RTDETR, YOLO
        model = (RTDETR if "rtdetr" in a.model.lower() else YOLO)(a.model)
        per = {}
        for v in sorted(VID.glob("*.mp4")):
            rows = dump(model, v, a.stride, a.tiles, a.imgsz)
            per[v.stem] = (rows, gt_start(GT / (v.stem + ".xml")))
            print(f"  덤프 {v.stem} ({len(rows)}표본)", flush=True)
        json.dump({k: {"rows": v[0], "gt": v[1]} for k, v in per.items()},
                  open(tl, "w"))
        print(f"시계열 저장: {tl}", flush=True)

    print(f"\n===== {a.tag} (tiles={a.tiles} imgsz={a.imgsz}) =====", flush=True)
    print("\n[영상별 신호] 정답시각 앞뒤 구간에서 실제로 신호가 있었는가", flush=True)
    print(f"  {'영상':22s} {'GT':>5} {'구간최대fire':>12} {'구간최대smoke':>13} {'전체최대fire':>12}", flush=True)
    for stem, (rows, gt) in sorted(per.items()):
        seg = [(bf, bs) for t, bf, bs in rows if gt - 10 <= t <= gt + 20]
        mf = max((x[0] for x in seg), default=0.0)
        ms = max((x[1] for x in seg), default=0.0)
        allf = max((bf for _, bf, _ in rows), default=0.0)
        print(f"  {stem:22s} {gt:5.0f} {mf:12.3f} {ms:13.3f} {allf:12.3f}", flush=True)

    print("\n[규칙 스윕 상위 12]", flush=True)
    res = []
    for kind in ("fire_only", "combined", "smoke_ok"):
        for fire in (0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5):
            for smoke in (0.3, 0.4, 0.5, 0.6, 0.7):
                for window, hits in ((3, 2), (5, 3), (6, 4), (8, 5), (10, 6), (12, 8)):
                    res.append((*score(per, kind, fire, smoke, window, hits), kind, fire, smoke, window, hits))
    res.sort(key=lambda x: (-x[0], x[3]))
    for r in res[:12]:
        print(f"  {r[0]:6.2f} (정검 {r[1]} 미검 {r[2]} 오검 {r[3]})  {r[5]:10s} f{r[6]} s{r[7]} {r[9]}/{r[8]}", flush=True)

    b = res[0]
    print(f"\n[최고 설정 영상별] {b[5]} f{b[6]} s{b[7]} {b[9]}/{b[8]}", flush=True)
    for stem, gt, sa, v in b[4]:
        print(f"  {stem:22s} GT {gt:5.0f}  SA {'-' if sa is None else f'{sa:7.1f}'}  {v}", flush=True)


if __name__ == "__main__":
    main()

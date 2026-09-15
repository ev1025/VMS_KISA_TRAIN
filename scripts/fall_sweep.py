# -*- coding: utf-8 -*-
# 기준 확인: th 0.269 need 4 로 재면 90.00 이 나와 제출 경로 실측과 같다(2026-09-15).
#            그래서 이 파일의 스윕 결과를 신뢰할 수 있다.
"""쓰러짐 판정 규칙(문턱 th · 연속 창 수 need)을 훑어 최고 조합을 찾는다.

왜 이렇게 하나
    쓰러짐은 학습을 새로 하지 않는다. yolo11x-pose 로 키포인트를 뽑고 SeqNet(fall_track.pt)이
    10초 창마다 점수를 내면, 그 점수를 어떻게 읽을지(th 이상이 need 창 연속)만 우리가 정한다.
    그래서 추론을 한 번만 돌려 창별 점수를 받아 두면, 규칙은 파일만 읽어 즉시 훑을 수 있다.
    (10편 추론이 1280 에서 약 10분. 조합마다 다시 돌리면 몇 시간이 된다.)

    문턱을 1.1 로 두면 어떤 창도 넘지 못해 발화가 안 되고, 그 덕에 영상 끝까지 점수가 쌓인다
    (실제 판정은 첫 발화에서 멈추므로 그 뒤 구간이 안 남는다). fall_res.py 가 쓰던 수법이다.

발화 시각 계산
    실제 판정기는 연속 need 창을 채운 순간 tr["ts"][-need] 를 발화 시각으로 쓴다.
    슬롯은 0.5초 간격으로 빠짐없이 쌓이므로, 창끝 시각에서 (need-1)*0.5 를 빼면 같은 값이다.

채점
    KISA 정상검출 = GT-2초 ~ GT+10초. 창을 벗어나면 오검과 미검을 같이 먹는다.
    F1 = 2*정검 / (2*정검 + 미검 + 오검) * 100.

사용
    python scripts/fall_sweep.py                 # 1280 으로 덤프 없으면 만들고 스윕
    python scripts/fall_sweep.py --imgsz 960
    python scripts/fall_sweep.py --redump        # 덤프를 다시 만든다
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import cv2

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_paths as KP           # noqa: E402

SLOT = 0.5                        # 창 판정 간격(FALL_SUB * FALL_STRIDE)
WIN_LO, WIN_HI = -2.0, 10.0       # 정상검출 유효창


def sig(z):
    return 1.0 / (1.0 + math.exp(-z))


def gt_of(mp4):
    """같은 폴더의 GT xml 에서 알람 시각(초). score_kisa.gt_start 와 같은 규칙
    (요소 이름은 Alarm 이고 StartTime 은 시:분:초)."""
    import xml.etree.ElementTree as ET
    x = mp4.with_suffix(".xml")
    if not x.is_file():
        return None
    al = ET.parse(x).getroot().find(".//Alarm")
    if al is None:
        return None
    s = al.findtext("StartTime")
    if not s:
        return None
    h, m, sec = (int(v) for v in s.split(":"))
    return h * 3600 + m * 60 + sec


def dump_clip(mp4, imgsz, out):
    """한 편을 끝까지 돌려 트랙별 (창끝 시각, 로짓) 을 남긴다."""
    import kisa_items as K
    cfg = K.ITEMS["falldown"]
    judge = K.FallJudge(K.WEIGHTS / cfg["model"], K.WEIGHTS / "fall_track.pt",
                        1.1, cfg["need"], None, imgsz)      # th 1.1 = 발화 안 함 → 끝까지 쌓인다
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * cfg["stride"]))
    i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                judge.feed(i / fps, fr)
        i += 1
    cap.release()
    curves = [tr["curve"] for tr in judge.tracks if tr.get("curve")]
    out.write_text(json.dumps({"imgsz": imgsz, "fps": round(fps, 3), "curves": curves}), encoding="utf-8")
    return curves


def fire_time(curves, th, need):
    """이 규칙에서 이 편이 알람을 내는 시각. 없으면 None."""
    best = None
    for cur in curves:
        run = 0
        for t, z in cur:
            run = run + 1 if sig(z) >= th else 0
            if run >= need:
                t0 = t - (need - 1) * SLOT
                best = t0 if best is None else min(best, t0)
                break
    return best


def score(clips, th, need):
    """정검·미검·오검과 F1. 창 밖 알람은 오검과 미검을 같이 먹는다(KISA 규정)."""
    tp = fn = fp = 0
    detail = []
    for stem, gt, curves in clips:
        sa = fire_time(curves, th, need)
        if sa is not None and gt + WIN_LO <= sa <= gt + WIN_HI:
            tp += 1; detail.append((stem, "정검", sa))
        elif sa is None:
            fn += 1; detail.append((stem, "미검", None))
        else:
            fn += 1; fp += 1; detail.append((stem, "오검", sa))
    f1 = 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0
    return f1, tp, fn, fp, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--redump", action="store_true")
    a = ap.parse_args()

    vids = sorted(p for p in KP.videos("쓰러짐").rglob("*.mp4"))
    dd = V / "dumps" / f"fall_seq_{a.imgsz}"
    dd.mkdir(parents=True, exist_ok=True)
    print(f"쓰러짐 {len(vids)}편 · 자세 해상도 {a.imgsz} · 덤프 {dd.relative_to(V)}")

    clips = []
    t0 = time.time()
    for k, mp4 in enumerate(vids, 1):
        gt = gt_of(mp4)
        if gt is None:
            print(f"  [GT 없음] {mp4.stem}"); continue
        f = dd / (mp4.stem + ".json")
        if f.is_file() and not a.redump:
            curves = json.loads(f.read_text(encoding="utf-8"))["curves"]
        else:
            curves = dump_clip(mp4, a.imgsz, f)
            print(f"  [{k}/{len(vids)}] {mp4.stem} 트랙 {len(curves)}개 · 경과 {(time.time()-t0)/60:.1f}분", flush=True)
        clips.append((mp4.stem, gt, curves))

    if not clips:
        print("채점할 편이 없습니다."); return 1

    cur_th, cur_need = 0.269, 4                     # 지금 쓰는 값(kisa_items.ITEMS['falldown'])
    rows = []
    for th in [0.15, 0.20, 0.25, 0.269, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]:
        for need in (3, 4, 5, 6, 7, 8):
            f1, tp, fn, fp, _ = score(clips, th, need)
            rows.append((f1, th, need, tp, fn, fp))
    rows.sort(key=lambda r: (-r[0], r[1], r[2]))

    print(f"\n=== 규칙 스윕 ({len(clips)}편) ===")
    seen = set()
    for f1, th, need, tp, fn, fp in rows[:14]:
        mark = "  ← 지금 값" if (th, need) == (cur_th, cur_need) else ""
        print(f"  th {th:<5} need {need}  →  {f1:6.2f}  (정검 {tp} 미검 {fn} 오검 {fp}){mark}")
        seen.add((th, need))
    if (cur_th, cur_need) not in seen:
        f1, tp, fn, fp, _ = score(clips, cur_th, cur_need)
        print(f"  th {cur_th:<5} need {cur_need}  →  {f1:6.2f}  (정검 {tp} 미검 {fn} 오검 {fp})  ← 지금 값")

    best_f1, best_th, best_need = rows[0][:3]
    print(f"\n=== 최고 조합 th {best_th} need {best_need} → {best_f1:.2f} · 편별 ===")
    _, _, _, _, detail = score(clips, best_th, best_need)
    for stem, verdict, sa in detail:
        gt = next(g for s, g, _ in clips if s == stem)
        off = f"{sa - gt:+.1f}s" if sa is not None else "—"
        print(f"  {stem}: {verdict}  (gt={gt:.1f} sa={sa if sa is None else round(sa, 1)} 차이 {off})")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def loocv(clips, grid):
    '''한 편을 빼고 나머지로 규칙을 고른 뒤, 뺀 편을 맞히는지 본다.

    같은 10편으로 고른 설정을 그 10편으로 채점하면 점수가 부풀려진다(방화 스윕이 그 예다).
    편마다 '이 편을 안 보고 고른 규칙' 으로 판정해 합산하면 낙관이 빠진 값이 된다.
    '''
    tp = fn = fp = 0
    picks = []
    for i, held in enumerate(clips):
        rest = clips[:i] + clips[i + 1:]
        best = max(grid, key=lambda c: (score(rest, *c)[0], -c[1], -c[0]))
        f1, t1, n1, p1, det = score([held], *best)
        picks.append((held[0], best, det[0][1]))
        tp += t1; fn += n1; fp += p1
    f1 = 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0
    return f1, tp, fn, fp, picks

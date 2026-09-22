# -*- coding: utf-8 -*-
"""1280 피처 분류기의 시드·피처 변형을 빠르게 선별한다(2026-09-20 밤).

무엇을 보나
    시드 0~4 각각(단일 모델)과 5시드 평균(앙상블), 그리고 '키포인트 신뢰도 채널을 0 으로 지운 피처'(제미나이 제안: 픽셀 ±1 에 가장 흔들리는 값 제거) 변형.
    잣대 두 개: (1) 채점 견본 10편 = feats/fall_kpts_1280 의 C00_ 편을 fall_track 오프라인 경로(트랙 → 창 → 곡선)로 채점 (2) 330편 6겹 교차검증(fall_cv330 함수 재사용).
    오프라인 경로는 배포 판정기와 완전히 같지는 않다(트랙 연결·패딩은 같은 규칙). 후보를 고른 뒤 배포 판정기(dump)로 확인한다.

사용
    .venv/bin/python scripts/fall_seed_screen.py [--seeds 5] [--device cuda]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import fall_track as FT      # noqa: E402
import fall_cv330 as CV      # noqa: E402
import fall_sweep as F       # noqa: E402
import kisa_items as K       # noqa: E402

KPTS = V / "feats/fall_kpts_1280"
CONF_IDX = [8 + 3 * k + 2 for k in range(17)]     # 59차원 중 키포인트 신뢰도 채널


def zero_conf(clips):
    """트랙 피처의 키포인트 신뢰도 채널을 0 으로(학습·평가 모두). 원본은 건드리지 않는다."""
    out = []
    for s, gt, dur, trs in clips:
        trs2 = []
        for ts, xs, pres in trs:
            xs2 = xs.copy(); xs2[:, CONF_IDX] = 0.0
            trs2.append((ts, xs2, pres))
        out.append((s, gt, dur, trs2))
    return out


def score(clips_curves, th, need, delay):
    tp = fn = fp = 0; bad = []
    for s, g, cur in clips_curves:
        sa = F.fire_time(cur, th, need)
        if sa is None:
            fn += 1; bad.append(s[4:] + "미"); continue
        sa += delay
        if g - 2 <= sa <= g + 10:
            tp += 1
        else:
            fn += 1; fp += 1; bad.append("%s오%+.0f" % (s[4:], sa - g))
    return 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0, tp, fn, fp, bad


def cv_score(train_clips, folds, seed, th, need, delay, nets_per_fold=1):
    """장면 묶음 교차검증 점수(fall_cv330 과 같은 겹 배정)."""
    fold_of, _ = CV.folds_by_scene(train_clips, folds, 0)
    win = {s: CV.clip_windows(gt, dur, trs) for s, gt, dur, trs in train_clips}
    curves = []
    for f in range(folds):
        tr = [c for c in train_clips if fold_of[c[0].split("_")[0]] != f]
        te = [c for c in train_clips if fold_of[c[0].split("_")[0]] == f]
        pos = [w for c in tr for w in win[c[0]][0]]; neg = [w for c in tr for w in win[c[0]][1]]
        nets = [CV.train(pos, neg, seed + k)[0] for k in range(nets_per_fold)]
        for s, gt, _d, trs in te:
            curves.append((s, gt, CV.curves_of(nets, trs)))
    return score(curves, th, need, delay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--folds", type=int, default=6)
    a = ap.parse_args()
    CV.DEV = torch.device(a.device)
    cfg = K.ITEMS["falldown"]; th, need, delay = cfg["th"], cfg["need"], float(cfg.get("delay", 0.0))
    files = sorted(KPTS.glob("*.npz"))
    t0 = time.time(); allc = CV.prep(files)
    train_clips = [c for c in allc if not c[0].startswith(FT.DEPLOY_PREFIX)]
    eval_clips = [c for c in allc if c[0].startswith(FT.DEPLOY_PREFIX)]
    print(f"전처리 {len(allc)}편 {time.time() - t0:.0f}s · 학습 {len(train_clips)} · 채점 견본 {len(eval_clips)} · 규칙 {th}·{need}·지연 {delay}", flush=True)

    for variant, fn in (("기본 59차원", lambda c: c), ("신뢰도 채널 0", zero_conf)):
        tr = fn(train_clips); ev = fn(eval_clips)
        win = {s: CV.clip_windows(gt, dur, trs) for s, gt, dur, trs in tr}
        pos = [w for c in tr for w in win[c[0]][0]]; neg = [w for c in tr for w in win[c[0]][1]]
        print(f"\n== {variant}")
        nets = []
        for seed in range(a.seeds):
            net = CV.train(pos, neg, seed)[0]; nets.append(net)
            ev_curves = [(s, gt, CV.curves_of([net], trs)) for s, gt, _d, trs in ev]
            f1, tp, fn_, fp, bad = score(ev_curves, th, need, delay)
            cvs = cv_score(tr, a.folds, seed, th, need, delay)
            print(f"   시드 {seed}: 견본 {f1:6.2f} ({tp}/{fn_}/{fp}) {','.join(bad):<24} 교차검증 {cvs[0]:6.2f} ({cvs[1]}/{cvs[2]}/{cvs[3]})", flush=True)
        ev_curves = [(s, gt, CV.curves_of(nets, trs)) for s, gt, _d, trs in ev]
        f1, tp, fn_, fp, bad = score(ev_curves, th, need, delay)
        cvs = cv_score(tr, a.folds, 0, th, need, delay, nets_per_fold=a.seeds)
        print(f"   {a.seeds}시드 평균: 견본 {f1:6.2f} ({tp}/{fn_}/{fp}) {','.join(bad):<24} 교차검증 {cvs[0]:6.2f} ({cvs[1]}/{cvs[2]}/{cvs[3]})", flush=True)
        # 참고: 옛 분류기(640 학습)를 같은 오프라인 경로로
        if variant == "기본 59차원":
            net0 = FT.SeqNet(); net0.load_state_dict(torch.load(V / "runs/fall_track/fall_track.pt", map_location="cpu")); net0.to(CV.DEV)
            ev_curves = [(s, gt, CV.curves_of([net0], trs)) for s, gt, _d, trs in ev]
            f1, tp, fn_, fp, bad = score(ev_curves, th, need, delay)
            print(f"   (참고) 옛 분류기 640학습: 견본 {f1:6.2f} ({tp}/{fn_}/{fp}) {','.join(bad)}", flush=True)
    print("끝", flush=True)


if __name__ == "__main__":
    main()

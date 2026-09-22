# -*- coding: utf-8 -*-
"""1280 피처 쓰러짐 분류기 변형을 330편 전체로 학습해 저장한다(2026-09-21).

변형
    --feat-noise S   학습 창에 가우시안 잡음 S(정규화 단위)를 더해 픽셀 ±1 잡음에 둔감한 분류기를 노린다.
    --seeds 0,1,2,3,4
    --kpts 폴더들(쉼표)  여러 피처 폴더(예: 원본 + 잡음 픽셀로 다시 뽑은 것)를 합쳐 학습.
저장: runs/fall_track_1280/<tag>_s<seed>.pt
사용: .venv/bin/python scripts/fall_train_variants.py --tag fn01 --feat-noise 0.01 --seeds 0,1,2,3,4 [--device cuda]
"""
import argparse
import sys
import time
from pathlib import Path

import torch

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import fall_track as FT      # noqa: E402
import fall_cv330 as CV      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--feat-noise", type=float, default=0.0)
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--kpts", default=str(V / "feats/fall_kpts_1280"))
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    CV.DEV = torch.device(a.device); CV.FEAT_NOISE = a.feat_noise
    out = V / "runs/fall_track_1280"; out.mkdir(parents=True, exist_ok=True)
    files = []
    for d in a.kpts.split(","):
        files += sorted(p for p in Path(d).glob("*.npz") if not p.stem.startswith(FT.DEPLOY_PREFIX))
    t0 = time.time(); clips = CV.prep(files)
    win = {}
    for i, (s, gt, dur, trs) in enumerate(clips):
        win[i] = CV.clip_windows(gt, dur, trs)
    pos = [w for v in win.values() for w in v[0]]; neg = [w for v in win.values() for w in v[1]]
    print(f"[{a.tag}] 피처 {a.kpts} · 편 {len(clips)} · 양성창 {len(pos)} 음성창 {len(neg)} · 잡음 {a.feat_noise} · 전처리 {time.time() - t0:.0f}s", flush=True)
    for seed in [int(x) for x in a.seeds.split(",")]:
        net, npos, nneg, loss = CV.train(pos, neg, seed)
        f = out / f"{a.tag}_s{seed}.pt"; torch.save(net.state_dict(), f)
        print(f"  시드 {seed}: loss {loss:.4f} → {f.name}", flush=True)
    print("끝", flush=True)


if __name__ == "__main__":
    main()

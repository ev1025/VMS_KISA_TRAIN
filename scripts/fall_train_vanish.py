# -*- coding: utf-8 -*-
"""쓰러짐 분류기 3벌을 '사라지는 음성'(fall_cv330.vanish_negs)과 함께 330편 전부로 다시 학습한다(2026-09-30 밤).
판정기 조합과 같은 3벌: 640 피처 시드 0(fall_track.pt 자리) · 1280 피처 시드 0 · 시드 1. 레시피는 fall_cv330.train 그대로.
--vanish 0 이면 같은 스크립트로 새 음성 없이 학습한 짝(비교 기준)이 나온다. 배포 파일은 덮지 않는다.
출력 = runs/fall_vanish/<실행시각>_v<vanish>/{fall_track.pt, fall_track_1280_s0.pt, fall_track_1280_s1.pt, meta.json}
  CUDA_VISIBLE_DEVICES= .venv/bin/python scripts/fall_train_vanish.py --vanish 1.0 [--threads 8]"""
import argparse
import json
import sys
import time
from pathlib import Path

import torch

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import fall_cv330 as CV   # noqa: E402
import fall_track as FT   # noqa: E402

NETS = (("feats/fall_kpts", "fall_track.pt", 0), ("feats/fall_kpts_1280", "fall_track_1280_s0.pt", 0),
        ("feats/fall_kpts_1280", "fall_track_1280_s1.pt", 1))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vanish", type=float, required=True)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    out = V / "runs/fall_vanish" / f"{time.strftime('%Y%m%d_%H%M')}_v{a.vanish:g}"
    out.mkdir(parents=True, exist_ok=True)
    cache, meta = {}, {"vanish": a.vanish, "recipe": "fall_cv330.train(12 epoch, AdamW 1e-3, 음성 3배) + vanish_negs", "nets": {}}
    for kpts, name, seed in NETS:
        if kpts not in cache:
            files = sorted(p for p in (V / kpts).glob("*.npz") if not p.stem.startswith(FT.DEPLOY_PREFIX))
            clips = CV.prep(files)
            win = {s: CV.clip_windows(gt, dur, trs) for s, gt, dur, trs in clips}
            cache[kpts] = ([w for c in clips for w in win[c[0]][0]], [w for c in clips for w in win[c[0]][1]], len(clips))
        pos, neg, nclip = cache[kpts]
        van = CV.vanish_negs(neg, int(len(pos) * a.vanish), seed)
        t0 = time.time()
        net, npos, nneg, loss = CV.train(pos, neg, seed, extra_neg=van or None)
        torch.save(net.state_dict(), out / name)
        meta["nets"][name] = {"kpts": kpts, "seed": seed, "clips": nclip, "pos": npos, "neg": nneg, "vanish_negs": len(van), "loss": round(loss, 4)}
        print(f"{name}: {kpts} 시드 {seed} · 양성창 {npos} 음성창 {nneg}(사라지는 음성 {len(van)}) · loss {loss:.4f} · {time.time() - t0:.0f}s", flush=True)
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("끝", out, flush=True)

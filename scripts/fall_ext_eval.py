# -*- coding: utf-8 -*-
"""쓰러짐 분류기(SeqNet)를 학습 영상 전부로 학습해, 학습에 안 쓴 외부 영상(AI허브 35편 등)에 돌린다(2026-10-03).
'지금 그대로' 와 '다른 출처 편을 학습에 더함(--extra-kpts)' 을 같은 시드로 비교하려는 것. 학습 레시피는 fall_cv330 과 같다(대표 트랙 1개 양성 · 음성 3배 표집 · 12에폭).
  --set-gt-aihub 폴더   : fall_kpts.py 가 만든 시험 피처 npz 에 AI허브 json(annotations.event_frame)으로 정답 시각을 채운다(처음 한 번)
출력: dumps/fall_seq_ext_<시험 폴더 이름>_<tag>/<편>.json {imgsz, gt, gt_end, tod, curves} → scripts/fall_sweep330.py 로 훑는다
  python scripts/fall_ext_eval.py --test feats/fall_kpts_1280_aihub35 --set-gt-aihub data/원본데이터/aihub_침입쓰러짐영상/쓰러짐
  python scripts/fall_ext_eval.py --kpts feats/fall_kpts_1280 --test feats/fall_kpts_1280_aihub35 --meta-dir data/원본데이터/aihub_침입쓰러짐영상/쓰러짐 \\
         [--extra-kpts feats/fall_kpts_1280_swoon171] --seeds 3 --tag base --device cuda"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import fall_cv330 as CV  # noqa: E402
import fall_track as FT  # noqa: E402


def set_gt_aihub(test, meta_dir):
    import cv2
    n = 0
    for p in sorted(Path(test).glob("*.npz")):
        mp4 = Path(meta_dir) / f"{p.stem}.mp4"
        meta = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8"))
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; cap.release()
        ev = meta["annotations"]["event_frame"][0]
        z = dict(np.load(p)); z["gt_start"] = np.float64(round(ev[0] / fps, 2)); z["gt_dur"] = np.float64(round((ev[1] - ev[0]) / fps, 2))
        np.savez_compressed(p, **z); n += 1
    print("정답 채움", n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kpts", default=str(FT.KPTS)); ap.add_argument("--test", required=True)
    ap.add_argument("--extra-kpts", nargs="*", default=[]); ap.add_argument("--meta-dir", default=None)
    ap.add_argument("--set-gt-aihub", default=None); ap.add_argument("--seeds", type=int, default=3); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--imgsz", type=int, default=1280); ap.add_argument("--tag", default="base"); ap.add_argument("--device", default="cpu")
    ap.add_argument("--aug", type=float, default=0.0); ap.add_argument("--arch", default="gru", choices=["gru", "conv"])
    ap.add_argument("--pt", default=None, nargs="*", help="학습하지 않고 이 SeqNet 가중치로 돌린다(예: runs/fall_track/fall_track.pt = 배포 분류기를 같은 특징에, 2026-10-03)")
    a = ap.parse_args()
    if a.set_gt_aihub:
        return set_gt_aihub(a.test, a.set_gt_aihub)
    CV.DEV = torch.device(a.device); CV.AUG = a.aug; CV.ARCH = a.arch
    if a.pt:
        nets = []
        for w in a.pt:                                      # 여러 벌이면 로짓 평균(판정기 3벌 평균과 같음)
            net = FT.SeqNet(); net.load_state_dict(torch.load(w, map_location="cpu")); net.to(CV.DEV); net.eval(); nets.append(net)
        print(f"가중치 {len(nets)}벌 {a.pt} 로 돌림(학습 안 함)", flush=True)
    if not a.pt:
        clips = CV.prep(sorted(p for p in Path(a.kpts).glob("*.npz") if not p.stem.startswith(FT.DEPLOY_PREFIX)))
        xclips = CV.prep(sorted(p for d in a.extra_kpts for p in Path(d).glob("*.npz"))) if a.extra_kpts else []
        pos, neg = [], []
        for _s, gt, dur, trs in clips + xclips:
            p_, n_, _ = CV.clip_windows(gt, dur, trs); pos += p_; neg += n_
        print(f"학습 {len(clips)}편 + 더함 {len(xclips)}편 · 양성 창 {len(pos)} 음성 창 {len(neg)} · 시드 {a.seeds}", flush=True)
        nets = [CV.train(pos, neg, a.seed + k)[0] for k in range(a.seeds)]
        wd = V / f"dumps/fall_seq_ext_{Path(a.test).name}_{a.tag}"; wd.mkdir(parents=True, exist_ok=True)
        for k, n in enumerate(nets):                     # 분류기 가중치도 남긴다(배포 후보가 되면 그대로 쓴다)
            torch.save(n.state_dict(), wd / f"net_{a.arch}_s{a.seed + k}.pt")
    out = V / f"dumps/fall_seq_ext_{Path(a.test).name}_{a.tag}"; out.mkdir(parents=True, exist_ok=True)
    test = CV.prep(sorted(Path(a.test).glob("*.npz")))
    for s, gt, dur, trs in test:
        tod = "Day"
        if a.meta_dir and (Path(a.meta_dir) / f"{s}.json").is_file():
            meta = json.loads((Path(a.meta_dir) / f"{s}.json").read_text(encoding="utf-8"))
            tod = "Night" if meta.get("metadata", {}).get("night") else "Day"
        CV.dump(out, s, gt, CV.curves_of(nets, trs), a.imgsz, tod=tod, gt_end=round(gt + dur, 2))
    print(f"시험 {len(test)}편 → {out}. 훑기: python scripts/fall_sweep330.py {out}", flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""쓰러짐 시계열 모델 (플랜 Day8~9): 1D 피처 시퀀스 → 창 단위 '쓰러짐 진행중' 분류.

제미나이는 약지도(MIL) ActionFormer 를 제안했으나, 해외 GT 에 시작+지속시간이 모두
있어 구간 라벨 지도학습으로 충분 (더 쉬운 문제로 강등). 모델은 fallback 안이던
Conv1D+GRU 경량 시계열 분류기 (환경 리스크 없는 자체 구현).

학습: 해외 330편 피처(fall_seq/*.npz, gt_start>=0)에서 10초(20표본) 창 표집
  양성 = 창이 [GT, GT+dur] 와 50% 이상 겹침 / 음성 = 완전 밖
검증: 배포 10편의 창별 로짓 시퀀스를 npz 로 저장 (+간단 임계 스윕 F1 출력)
"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import kisa_paths as _KP   # 경로는 한 곳에서만 정한다(docs/file_path.md 1절)
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

FEATS = _KP.V / "feats/fall_seq"
OUT = _KP.V / "runs/fall_seq"
WIN = 20            # 10초 (0.5초 표본)
DIM = 59
DEPLOY_PREFIX = "C00_"      # 배포용 파일명, 해외는 C0xxxxx


class SeqNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(DIM, 96, 5, padding=2), nn.ReLU(),
            nn.Conv1d(96, 96, 5, padding=2), nn.ReLU())
        self.gru = nn.GRU(96, 96, num_layers=2, batch_first=True, bidirectional=True)
        self.head = nn.Linear(192, 1)

    def forward(self, x):                    # x: (B, T, D)
        h = self.conv(x.transpose(1, 2)).transpose(1, 2)
        h, _ = self.gru(h)
        return self.head(h[:, -1]).squeeze(-1)   # 창 끝 시점 기준 로짓


def load_all():
    train, deploy = [], []
    for p in sorted(FEATS.glob("*.npz")):
        z = np.load(p)
        item = (p.stem, z["t"], z["x"], float(z["gt_start"]), float(z["gt_dur"]))
        (deploy if p.stem.startswith(DEPLOY_PREFIX) else train).append(item)
    return train, deploy


def windows_of(t, x, gt, dur):
    """(창 텐서, 라벨) 생성. 라벨: 겹침>=50% 양성, 0% 음성, 그 사이는 버림."""
    out = []
    for e in range(WIN, len(t)):
        seg = x[e - WIN:e]
        t0, t1 = t[e - WIN], t[e - 1]
        if gt < 0:
            out.append((seg, 0))
            continue
        ov = max(0.0, min(t1, gt + dur) - max(t0, gt))
        frac = ov / (t1 - t0 + 1e-6)
        if frac >= 0.5:
            out.append((seg, 1))
        elif ov == 0:
            out.append((seg, 0))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(0)
    torch.manual_seed(0)
    train_v, deploy_v = load_all()
    print(f"학습 영상 {len(train_v)} · 배포 검증 {len(deploy_v)}")

    pos, neg = [], []
    for _, t, x, gt, dur in train_v:
        if len(t) < WIN + 1:
            continue
        for seg, y in windows_of(t, x, gt, max(dur, 5.0)):
            (pos if y else neg).append(seg)
    random.shuffle(neg)
    neg = neg[:len(pos) * 3]
    print(f"창 표본: 양성 {len(pos)} · 음성 {len(neg)}")

    X = torch.tensor(np.stack(pos + neg), dtype=torch.float32)
    Y = torch.tensor([1.0] * len(pos) + [0.0] * len(neg))
    idx = torch.randperm(len(X))
    X, Y = X[idx], Y[idx]

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = SeqNet().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.BCEWithLogitsLoss()
    B = 512
    for ep in range(12):
        net.train()
        tot = 0.0
        for i in range(0, len(X), B):
            xb, yb = X[i:i + B].to(dev), Y[i:i + B].to(dev)
            opt.zero_grad()
            loss = lossf(net(xb), yb)
            loss.backward()
            opt.step()
            tot += float(loss) * len(xb)
        print(f"ep{ep + 1}: loss {tot / len(X):.4f}", flush=True)
    torch.save(net.state_dict(), OUT / "fall_seq.pt")

    # 배포 10편 로짓 시퀀스 저장 + 간단 임계 스윕
    net.eval()
    logits_all = {}
    with torch.no_grad():
        for stem, t, x, gt, dur in deploy_v:
            if len(t) < WIN + 1:
                continue
            segs = np.stack([x[e - WIN:e] for e in range(WIN, len(t))])
            lo = []
            for i in range(0, len(segs), B):
                lo.append(net(torch.tensor(segs[i:i + B], dtype=torch.float32).to(dev)).cpu().numpy())
            logits_all[stem] = (t[WIN:], np.concatenate(lo), gt)
    np.savez_compressed(OUT / "deploy_logits.npz",
                        **{f"{k}__t": v[0] for k, v in logits_all.items()},
                        **{f"{k}__z": v[1] for k, v in logits_all.items()},
                        **{f"{k}__gt": np.array([v[2]]) for k, v in logits_all.items()})

    print("\n== 임계 스윕 (onset=임계 최초 돌파, 창 [-2,+10]) ==")
    for th in (0.0, 0.5, 1.0, 1.5, 2.0):
        tp = fn = fp = 0
        for stem, (t, z, gt) in logits_all.items():
            over = np.nonzero(z >= th)[0]
            o = float(t[over[0]]) if len(over) else None
            if o is None:
                fn += 1
            elif gt - 2 <= o <= gt + 10:
                tp += 1
            else:
                fp += 1
                fn += 1
        r = tp / (tp + fn) if tp + fn else 0
        p = tp / (tp + fp) if tp + fp else 0
        f1 = 2 * r * p / (r + p) * 100 if r + p else 0
        print(f"  th {th:.1f} → {f1:6.2f} (정검 {tp} 미검 {fn} 오검 {fp})", flush=True)


if __name__ == "__main__":
    main()

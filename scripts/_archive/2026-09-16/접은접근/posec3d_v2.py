# -*- coding: utf-8 -*-
"""PoseC3D v2 (메모리 안전): 원시 키포인트 → 히트맵 볼륨을 배치 생성(on-the-fly).
   v1 은 전체 창(60k×1.4MB≈84GB)을 한 배열로 쌓아 죽음. v2 는 인덱스만 들고 배치마다 렌더.
   쓰러짐 온셋: 스펙 = 머리가 바닥에 닿는 시각, 다수면 '처음 쓰러지는 사람' 기준."""
import glob, math, sys
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
FEAT = G/"feats"/"fall_kpts"
HW, WIN, STRIDE_W, SIGMA = 28, 16, 4, 1.6
BEFORE, AFTER = 2.0, 10.0
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")
YS, XS = np.mgrid[0:HW, 0:HW]


def render(kp_win, wh):
    """(WIN,maxp,17,3) → (17,WIN,HW,HW) float32. 사람 합산, conf 가중."""
    W = max(int(wh[0]), 1); H = max(int(wh[1]), 1)
    vol = np.zeros((17, WIN, HW, HW), np.float32)
    for t in range(kp_win.shape[0]):
        for p in range(kp_win.shape[1]):
            for j in range(17):
                x, y, c = kp_win[t, p, j]
                if c < 0.1 or (x == 0 and y == 0):
                    continue
                gx, gy = x/W*HW, y/H*HW
                vol[j, t] += c*np.exp(-((XS-gx)**2 + (YS-gy)**2)/(2*SIGMA**2))
    return np.clip(vol, 0, 1)


def index_videos():
    """영상별 (kpts, wh, t, gt, 창 시작 인덱스 목록, 라벨)"""
    vids = {}
    for f in sorted(glob.glob(str(FEAT/"*.npz"))):
        d = np.load(f)
        k, wh, ts = d["kpts"], d["wh"], d["t"]
        gs = float(d["gt_start"]); gs = None if gs < 0 else gs
        if len(k) < WIN:
            continue
        starts, labels = [], []
        for s in range(0, len(k)-WIN+1, STRIDE_W):
            t0, t1 = float(ts[s]), float(ts[s+WIN-1])
            lab = 0
            if gs is not None:
                # 창 안에서 온셋을 내면 정검이 되는가
                lab = 1 if (gs-BEFORE <= t1 <= gs+AFTER) else 0
            starts.append(s); labels.append(lab)
        vids[Path(f).stem] = dict(k=k, wh=wh, ts=ts, gt=gs, starts=starts, labels=labels)
    return vids


class C3D(nn.Module):
    def __init__(s):
        super().__init__()
        s.net = nn.Sequential(
            nn.Conv3d(17, 32, 3, padding=1), nn.BatchNorm3d(32), nn.ReLU(),
            nn.MaxPool3d((1, 2, 2)),
            nn.Conv3d(32, 64, 3, padding=1), nn.BatchNorm3d(64), nn.ReLU(),
            nn.MaxPool3d(2),
            nn.Conv3d(64, 128, 3, padding=1), nn.BatchNorm3d(128), nn.ReLU(),
            nn.AdaptiveAvgPool3d(1))
        s.fc = nn.Sequential(nn.Dropout(0.5), nn.Linear(128, 1))
    def forward(s, x):
        return s.fc(s.net(x).flatten(1)).squeeze(-1)


def batches(vids, names, bs, shuffle=True):
    items = [(n, i) for n in names for i in range(len(vids[n]["starts"]))]
    if shuffle:
        np.random.shuffle(items)
    for b in range(0, len(items), bs):
        chunk = items[b:b+bs]
        X = np.stack([render(vids[n]["k"][vids[n]["starts"][i]:vids[n]["starts"][i]+WIN], vids[n]["wh"]) for n, i in chunk])
        y = np.array([vids[n]["labels"][i] for n, i in chunk], np.float32)
        yield torch.from_numpy(X), torch.from_numpy(y), chunk


def main():
    vids = index_videos()
    names = sorted(vids)
    nwin = sum(len(vids[n]["starts"]) for n in names)
    npos = sum(sum(vids[n]["labels"]) for n in names)
    print(f"영상 {len(names)} · 창 {nwin} (양성 {npos})", flush=True)

    np.random.seed(0)
    order = names[:]; np.random.shuffle(order)
    folds = [order[i::5] for i in range(5)]
    ths = [0.3, 0.4, 0.5, 0.6, 0.7]
    agg = {t: dict(tp=0, fn=0, fp=0) for t in ths}

    for fi, test in enumerate(folds):
        train = [n for n in names if n not in test]
        model = C3D().to(DEV)
        opt = torch.optim.AdamW(model.parameters(), 1e-3, weight_decay=1e-4)
        pw = torch.tensor([max(1.0, (nwin-npos)/max(1, npos))]).to(DEV)
        lossf = nn.BCEWithLogitsLoss(pos_weight=pw)
        model.train()
        for ep in range(4):
            for X, y, _ in batches(vids, train, 32):
                X, y = X.to(DEV), y.to(DEV)
                opt.zero_grad(); loss = lossf(model(X), y); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            for n in test:
                probs = {}
                for X, _, chunk in batches(vids, [n], 32, shuffle=False):
                    p = torch.sigmoid(model(X.to(DEV))).cpu().numpy()
                    for (nn_, i), pi in zip(chunk, p):
                        probs[i] = float(pi)
                v = vids[n]; gt = v["gt"]
                for th in ths:
                    sa = None
                    for i in sorted(probs):
                        if probs[i] >= th:
                            sa = float(v["ts"][v["starts"][i]+WIN-1]); break
                    if gt is None:
                        if sa is not None: agg[th]["fp"] += 1
                    elif sa is not None and gt-BEFORE <= sa <= gt+AFTER:
                        agg[th]["tp"] += 1
                    else:
                        agg[th]["fn"] += 1
                        if sa is not None: agg[th]["fp"] += 1
        print(f"fold {fi+1}/5 완료", flush=True)

    print("\n=== PoseC3D v2 (5-fold) ===")
    best = 0
    for th in ths:
        a = agg[th]
        r = a["tp"]/(a["tp"]+a["fn"]) if a["tp"]+a["fn"] else 0
        p = a["tp"]/(a["tp"]+a["fp"]) if a["tp"]+a["fp"] else 0
        f1 = 2*r*p/(r+p)*100 if r+p else 0
        best = max(best, f1)
        print(f"  th {th}: F1 {f1:5.1f} (정검 {a['tp']} 미검 {a['fn']} 오검 {a['fp']})")
    print(f"최고 {best:.1f}  vs  기존 시계열(BiGRU) 84.2")


if __name__ == "__main__":
    main()

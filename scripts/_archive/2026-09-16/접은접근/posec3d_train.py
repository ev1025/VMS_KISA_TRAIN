# -*- coding: utf-8 -*-
"""경량 PoseC3D 식 쓰러짐 분류기: 원시 키포인트 → 히트맵 볼륨(T,17,H,W) → 3D-CNN.
   fall_kpts/*.npz (kpts (T,maxp,17,3) 절대px, wh, gt_start, gt_dur).
   창=2초(WIN 프레임), 겹침 GT면 양성. 비디오단위 LOOCV, 임계 스윕. 목표=84.2 초과.
   fall_seq(BiGRU 84.2)와 다른 점: 좌표 붕괴(0,0) 대신 확률 히트맵이라 폐색·저신뢰 인물 보존."""
import glob, sys
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
FEAT = G / "feats/fall_kpts"
HW = 32          # 히트맵 해상도
WIN = 20         # 2초(10fps)
STRIDE_W = 5
SIGMA = 1.5
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def heatmap_vol(kpts, wh):
    """(T,maxp,17,3) → (T,17,HW,HW) 가우시안 히트맵 합(사람 합산, conf 가중)"""
    T = kpts.shape[0]
    W, H = (wh[0] or 1), (wh[1] or 1)
    vol = np.zeros((T, 17, HW, HW), np.float32)
    ys, xs = np.mgrid[0:HW, 0:HW]
    for t in range(T):
        for p in range(kpts.shape[1]):
            for j in range(17):
                x, y, c = kpts[t, p, j]
                if c < 0.1 or (x == 0 and y == 0):
                    continue
                gx, gy = x / W * HW, y / H * HW
                vol[t, j] += c * np.exp(-((xs - gx) ** 2 + (ys - gy) ** 2) / (2 * SIGMA ** 2))
    return np.clip(vol, 0, 1)


def windows(npz):
    d = np.load(npz)
    k, wh = d["kpts"], d["wh"]
    gs, gd = float(d["gt_start"]), float(d["gt_dur"])
    ts = d["t"]
    if len(k) < WIN:
        return []
    vol = heatmap_vol(k, wh)                          # (T,17,HW,HW)
    out = []
    for s in range(0, len(k) - WIN + 1, STRIDE_W):
        w = vol[s:s + WIN]                            # (WIN,17,HW,HW)
        t0, t1 = ts[s], ts[s + WIN - 1]
        pos = 0
        if gs >= 0:
            ge = gs + max(gd, 2)
            ov = max(0, min(t1, ge) - max(t0, gs))
            pos = 1 if ov >= (t1 - t0) * 0.5 else 0
        out.append((w.transpose(1, 0, 2, 3), pos, t0, gs))   # (17,WIN,HW,HW)
    return out


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


def main():
    files = sorted(glob.glob(str(FEAT / "*.npz")))
    print(f"영상 {len(files)}편 → 히트맵 창 생성...", flush=True)
    per_vid = {}
    for f in files:
        w = windows(f)
        if w:
            per_vid[Path(f).stem] = w
    vids = list(per_vid)
    print(f"창 보유 영상 {len(vids)}", flush=True)

    # 비디오단위 LOOCV — 무거우니 5-fold 로 근사
    import random
    random.seed(0); random.shuffle(vids)
    folds = [vids[i::5] for i in range(5)]
    ths = [0.3, 0.4, 0.5, 0.6, 0.7]
    agg = {th: dict(tp=0, fn=0, fp=0) for th in ths}
    DELAY, BEFORE, AFTER = 0.0, 2.0, 10.0   # 쓰러짐 SA=onset (지연 0)

    for fi, test in enumerate(folds):
        train = [v for v in vids if v not in test]
        Xtr = np.array([w for v in train for w, y, t0, gs in per_vid[v]], np.float32)
        ytr = np.array([y for v in train for w, y, t0, gs in per_vid[v]], np.float32)
        model = C3D().to(DEV)
        opt = torch.optim.AdamW(model.parameters(), 1e-3, weight_decay=1e-4)
        lossf = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([(ytr == 0).sum() / max(1, (ytr == 1).sum())]).to(DEV))
        idx = np.arange(len(Xtr))
        model.train()
        for ep in range(8):
            np.random.shuffle(idx)
            for b in range(0, len(idx), 64):
                bi = idx[b:b + 64]
                xb = torch.tensor(Xtr[bi]).to(DEV); yb = torch.tensor(ytr[bi]).to(DEV)
                opt.zero_grad(); out = model(xb); loss = lossf(out, yb); loss.backward(); opt.step()
        # 평가: 영상별 첫 임계초과 창의 onset → SA
        model.eval()
        with torch.no_grad():
            for v in test:
                W_ = per_vid[v]
                probs = []
                for b in range(0, len(W_), 64):
                    xb = torch.tensor(np.array([w for w, y, t0, gs in W_[b:b + 64]], np.float32)).to(DEV)
                    probs += torch.sigmoid(model(xb)).cpu().numpy().tolist()
                gs = W_[0][3]
                for th in ths:
                    sa = None
                    for (w, y, t0, g), pr in zip(W_, probs):
                        if pr >= th:
                            sa = t0 + DELAY; break
                    if gs < 0:
                        if sa is not None: agg[th]["fp"] += 1
                    elif sa is not None and gs - BEFORE <= sa <= gs + AFTER:
                        agg[th]["tp"] += 1
                    else:
                        agg[th]["fn"] += 1
                        if sa is not None: agg[th]["fp"] += 1
        print(f"fold {fi+1}/5 완료", flush=True)

    print("\n=== PoseC3D LOOCV(5-fold 근사) ===")
    best = 0
    for th in ths:
        a = agg[th]; r = a["tp"] / (a["tp"] + a["fn"]) if a["tp"] + a["fn"] else 0
        p = a["tp"] / (a["tp"] + a["fp"]) if a["tp"] + a["fp"] else 0
        f1 = 2 * r * p / (r + p) * 100 if r + p else 0
        best = max(best, f1)
        print(f"  th {th}: F1 {f1:.1f} (정검 {a['tp']} 미검 {a['fn']} 오검 {a['fp']})")
    print(f"최고 {best:.1f} vs fall_seq(BiGRU) 84.2")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""PoseC3D v3: 히트맵 렌더링을 GPU 벡터화 + 2fps 다운샘플.
   v2 실패 원인: 10fps × stride4 → 창 37만 개, CPU 반복문 렌더 → 사실상 안 끝남.
   v3: 5프레임마다(2fps) + 창 겹침 축소 → 창 3만 대, 렌더는 torch 브로드캐스트로 GPU.
   쓰러짐 스펙: 머리가 바닥에 닿는 시각, 다수면 '처음 쓰러지는 사람'."""
import glob, sys
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
FEAT = G/"feats"/"fall_kpts"
SUB = 5          # 10fps → 2fps
HW = 32
WIN = 20         # 10초
STRIDE_W = 8
SIGMA = 1.5
BEFORE, AFTER = 2.0, 10.0
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load():
    vids = {}
    for f in sorted(glob.glob(str(FEAT/"*.npz"))):
        d = np.load(f)
        k = d["kpts"][::SUB]                       # (T,P,17,3)
        ts = d["t"][::SUB]
        wh = d["wh"].astype(np.float32)
        gs = float(d["gt_start"]); gs = None if gs < 0 else gs
        if len(k) < WIN:
            continue
        # 정규화 좌표 + conf 로 변환 (미검출은 conf 0)
        kk = k.astype(np.float32).copy()
        kk[..., 0] /= max(float(wh[0]), 1.0)
        kk[..., 1] /= max(float(wh[1]), 1.0)
        bad = (kk[..., 2] < 0.1) | ((k[..., 0] == 0) & (k[..., 1] == 0))
        kk[..., 2][bad] = 0.0
        starts, labels = [], []
        for s in range(0, len(kk)-WIN+1, STRIDE_W):
            t1 = float(ts[s+WIN-1])
            lab = 1 if (gs is not None and gs-BEFORE <= t1 <= gs+AFTER) else 0
            starts.append(s); labels.append(lab)
        vids[Path(f).stem] = dict(k=kk, ts=ts, gt=gs, starts=starts, labels=labels)
    return vids


GY, GX = torch.meshgrid(torch.arange(HW), torch.arange(HW), indexing="ij")
GX = (GX.float()/(HW-1)).to(DEV); GY = (GY.float()/(HW-1)).to(DEV)


def render(batch_k):
    """(B,T,P,17,3) 정규화 → (B,17,T,HW,HW). torch 브로드캐스트, GPU."""
    kb = torch.from_numpy(batch_k).to(DEV)                 # B,T,P,J,3
    x = kb[..., 0].unsqueeze(-1).unsqueeze(-1)             # B,T,P,J,1,1
    y = kb[..., 1].unsqueeze(-1).unsqueeze(-1)
    c = kb[..., 2].unsqueeze(-1).unsqueeze(-1)
    d2 = (GX - x)**2 + (GY - y)**2                         # B,T,P,J,HW,HW
    hm = c * torch.exp(-d2/(2*(SIGMA/HW)**2))
    hm = hm.sum(dim=2)                                     # 사람 합산 → B,T,J,HW,HW
    return hm.clamp(0, 1).permute(0, 2, 1, 3, 4).contiguous()   # B,J,T,HW,HW


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
    def forward(s, x): return s.fc(s.net(x).flatten(1)).squeeze(-1)


def iter_batches(vids, names, bs, shuffle=True):
    items = [(n, i) for n in names for i in range(len(vids[n]["starts"]))]
    if shuffle: np.random.shuffle(items)
    for b in range(0, len(items), bs):
        ch = items[b:b+bs]
        X = np.stack([vids[n]["k"][vids[n]["starts"][i]:vids[n]["starts"][i]+WIN] for n, i in ch])
        y = np.array([vids[n]["labels"][i] for n, i in ch], np.float32)
        yield X, torch.from_numpy(y).to(DEV), ch


def main():
    vids = load(); names = sorted(vids)
    nwin = sum(len(vids[n]["starts"]) for n in names)
    npos = sum(sum(vids[n]["labels"]) for n in names)
    print(f"영상 {len(names)} · 창 {nwin} (양성 {npos}) · 장치 {DEV}", flush=True)

    np.random.seed(0); order = names[:]; np.random.shuffle(order)
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
        for ep in range(6):
            for X, y, _ in iter_batches(vids, train, 24):
                opt.zero_grad()
                loss = lossf(model(render(X)), y)
                loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            for n in test:
                probs = {}
                for X, _, ch in iter_batches(vids, [n], 24, shuffle=False):
                    p = torch.sigmoid(model(render(X))).cpu().numpy()
                    for (nn_, i), pi in zip(ch, p): probs[i] = float(pi)
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

    print("\n=== PoseC3D v3 (5-fold) ===")
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

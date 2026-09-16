# -*- coding: utf-8 -*-
"""쓰러짐 v2: 검증된 84.2 구조(가공피처+BiGRU) 유지 + 다인 처리 추가.
   기존 한계: top-1 한 명만 봐서 원거리·폐색 시 신호 소실(미검 2편).
   개선: 최대 5인 각각 피처 → 사람축 집계(최대/평균) → 시계열 분류.
   스펙: 다수가 쓰러지면 '처음 쓰러지는 사람' 기준."""
import glob, math
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
FEAT = G/"feats"/"fall_kpts"
SUB = 5                    # 10fps → 2fps (기존 84.2 와 동일 간격)
WIN, STRIDE_W = 20, 4      # 10초 창
BEFORE, AFTER = 2.0, 10.0
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def person_feats(kp, W, H):
    """(17,3) → 13차원 물리 피처. 미검출이면 0 벡터 + valid=0"""
    conf = kp[:, 2]
    if (conf > 0.1).sum() < 4:
        return np.zeros(13, np.float32)
    xs, ys = kp[:, 0]/max(W, 1), kp[:, 1]/max(H, 1)
    ok = conf > 0.1
    x1, x2 = xs[ok].min(), xs[ok].max(); y1, y2 = ys[ok].min(), ys[ok].max()
    w, h = max(x2-x1, 1e-4), max(y2-y1, 1e-4)
    sh = [i for i in (5, 6) if conf[i] > 0.1]; hp = [i for i in (11, 12) if conf[i] > 0.1]
    ang = 90.0
    if sh and hp:
        sx, sy = xs[sh].mean(), ys[sh].mean(); hx, hy = xs[hp].mean(), ys[hp].mean()
        a = abs(math.degrees(math.atan2(hy-sy, hx-sx))); ang = min(a, 180-a)
    nose_y = ys[0] if conf[0] > 0.1 else (ys[sh].mean() if sh else 0.0)
    foot = [i for i in (15, 16) if conf[i] > 0.1]
    foot_y = ys[foot].mean() if foot else y2
    return np.array([
        1.0,                       # valid
        float(conf[ok].mean()), float((conf > 0.1).mean()),
        float(w), float(h), float(w/h),          # 종횡비: 누우면 커짐
        float(ang/90.0),                          # 몸통 각도: 누우면 0에 가까움
        float(nose_y), float(foot_y),
        float(nose_y - foot_y),                   # 머리-발 높이차: 누우면 0
        float((y1+y2)/2), float((x1+x2)/2),
        float(h*w),
    ], np.float32)


def load():
    vids = {}
    for f in sorted(glob.glob(str(FEAT/"*.npz"))):
        d = np.load(f)
        k = d["kpts"][::SUB]; ts = d["t"][::SUB]; wh = d["wh"]
        gs = float(d["gt_start"]); gs = None if gs < 0 else gs
        T, P = k.shape[0], k.shape[1]
        if T < WIN: continue
        F = np.zeros((T, P, 13), np.float32)
        for t in range(T):
            for p in range(P):
                F[t, p] = person_feats(k[t, p], float(wh[0]), float(wh[1]))
        # 사람축 집계: 최대 + 평균 + 유효인원수 → 27차원
        agg = np.concatenate([F.max(axis=1), F.mean(axis=1), F[:, :, 0:1].sum(axis=1)], axis=1)
        starts, labels = [], []
        for s in range(0, T-WIN+1, STRIDE_W):
            t1 = float(ts[s+WIN-1])
            labels.append(1 if (gs is not None and gs-BEFORE <= t1 <= gs+AFTER) else 0)
            starts.append(s)
        vids[Path(f).stem] = dict(x=agg, ts=ts, gt=gs, starts=starts, labels=labels)
    return vids


class Seq(nn.Module):
    def __init__(s, d):
        super().__init__()
        s.c = nn.Sequential(nn.Conv1d(d, 64, 3, padding=1), nn.BatchNorm1d(64), nn.ReLU(),
                            nn.Conv1d(64, 64, 3, padding=1), nn.BatchNorm1d(64), nn.ReLU())
        s.g = nn.GRU(64, 64, 2, batch_first=True, bidirectional=True, dropout=0.3)
        s.f = nn.Sequential(nn.Dropout(0.5), nn.Linear(128, 1))
    def forward(s, x):              # x (B,T,D)
        h = s.c(x.transpose(1, 2)).transpose(1, 2)
        o, _ = s.g(h)
        return s.f(o.mean(dim=1)).squeeze(-1)


def main():
    vids = load(); names = sorted(vids)
    D = vids[names[0]]["x"].shape[1]
    nwin = sum(len(vids[n]["starts"]) for n in names)
    npos = sum(sum(vids[n]["labels"]) for n in names)
    print(f"영상 {len(names)} · 창 {nwin} (양성 {npos}) · 차원 {D}", flush=True)

    np.random.seed(0); order = names[:]; np.random.shuffle(order)
    folds = [order[i::5] for i in range(5)]
    ths = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    agg = {t: dict(tp=0, fn=0, fp=0) for t in ths}

    for fi, test in enumerate(folds):
        train = [n for n in names if n not in test]
        Xtr = np.stack([vids[n]["x"][s:s+WIN] for n in train for s in vids[n]["starts"]])
        ytr = np.array([l for n in train for l in vids[n]["labels"]], np.float32)
        model = Seq(D).to(DEV)
        opt = torch.optim.AdamW(model.parameters(), 1e-3, weight_decay=1e-4)
        pw = torch.tensor([max(1.0, (len(ytr)-ytr.sum())/max(1, ytr.sum()))]).to(DEV)
        lossf = nn.BCEWithLogitsLoss(pos_weight=pw)
        idx = np.arange(len(Xtr)); model.train()
        for ep in range(25):
            np.random.shuffle(idx)
            for b in range(0, len(idx), 128):
                bi = idx[b:b+128]
                xb = torch.from_numpy(Xtr[bi]).to(DEV); yb = torch.from_numpy(ytr[bi]).to(DEV)
                opt.zero_grad(); loss = lossf(model(xb), yb); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            for n in test:
                v = vids[n]
                X = np.stack([v["x"][s:s+WIN] for s in v["starts"]])
                p = torch.sigmoid(model(torch.from_numpy(X).to(DEV))).cpu().numpy()
                gt = v["gt"]
                for th in ths:
                    sa = None
                    for i, pi in enumerate(p):
                        if pi >= th: sa = float(v["ts"][v["starts"][i]+WIN-1]); break
                    if gt is None:
                        if sa is not None: agg[th]["fp"] += 1
                    elif sa is not None and gt-BEFORE <= sa <= gt+AFTER: agg[th]["tp"] += 1
                    else:
                        agg[th]["fn"] += 1
                        if sa is not None: agg[th]["fp"] += 1
        print(f"fold {fi+1}/5", flush=True)

    print("\n=== 쓰러짐 v2 (다인, 5-fold) ===")
    best = 0
    for th in ths:
        a = agg[th]
        r = a["tp"]/(a["tp"]+a["fn"]) if a["tp"]+a["fn"] else 0
        pr = a["tp"]/(a["tp"]+a["fp"]) if a["tp"]+a["fp"] else 0
        f1 = 2*r*pr/(r+pr)*100 if r+pr else 0
        best = max(best, f1)
        print(f"  th {th}: F1 {f1:5.1f} (정검 {a['tp']} 미검 {a['fn']} 오검 {a['fp']})")
    print(f"최고 {best:.1f}  vs  기존 84.2 · PoseC3D 43.0")


if __name__ == "__main__":
    main()

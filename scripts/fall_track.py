# -*- coding: utf-8 -*-
"""쓰러짐 KISA 스펙 규칙: '다수가 쓰러지면 처음 쓰러지는 사람' = 사람별 독립 판정 후 최초 발생.

기존 실패 2건의 원인:
  - fall_seq_v2 (다인 집계 27차원 max/mean): 여러 사람 신호를 한 벡터로 섞어 희석 → 29.6
  - PoseC3D (히트맵 3D CNN): 창 3.7만 개로 데이터 부족 → 43.0
이번 방식:
  - fall_kpts npz (10fps, 최대 5인, 절대 픽셀 키포인트) 를 프레임 간 중심거리로 이어붙여 '트랙' 생성
  - 트랙마다 검증된 59차원 피처를 만들고, 검증된 SeqNet(Conv1D+BiGRU) 을 트랙별로 독립 적용
  - 알람 시각 = 트랙들 중 가장 이른 임계 돌파 시각 (= 처음 쓰러지는 사람)
피처는 학습·추론 모두 같은 방식(키포인트로 만든 유사 박스)으로 만들어 분포를 맞춘다.
학습 라벨: 정답 구간에 존재하는 트랙 중 대표 1개(구간 내 평균 신뢰도 최대)만 양성, 구간 밖 창은 음성.
"""
import glob
import math
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

G = Path(__file__).resolve().parents[1]
KPTS = G / "feats/fall_kpts"
OUT = G / "runs/fall_track"
STRIDE_SRC = 0.1          # fall_kpts 저장 간격(초)
SUB = 5                   # 5프레임마다 = 0.5초 (검증된 fall_seq 와 동일한 시간 해상도)
WIN = 20                  # 창 20표본 = 10초
DIM = 59
KP_TH = 0.2               # 키포인트 유효 신뢰도
MAX_GAP = 8               # 트랙 끊김 허용 프레임(0.8초)
MIN_LEN = WIN + 1         # 창 하나는 만들 수 있어야 트랙으로 인정
BEFORE, AFTER = 2.0, 10.0
DEPLOY_PREFIX = "C00_"


# ---------------- 트랙 만들기 ----------------
def kp_center(kp):
    """유효 키포인트들의 중심. 없으면 None."""
    v = kp[kp[:, 2] >= KP_TH]
    if len(v) == 0:
        return None
    return float(v[:, 0].mean()), float(v[:, 1].mean())


def build_tracks(kpts):
    """kpts: (T, P, 17, 3) 절대픽셀. 슬롯은 프레임마다 신뢰도순이라 사람 신원이 안 맞음.
       프레임 간 중심거리 최소 짝짓기로 이어붙여 트랙(사람별 시계열)을 만든다.
       반환: [{frame_index: (17,3) 키포인트}] 리스트"""
    T, P = kpts.shape[0], kpts.shape[1]
    tracks = []          # 각 원소: dict(frames={}, last_c=(x,y), last_i=프레임번호)
    for ti in range(T):
        # 이번 프레임에서 사람으로 볼 슬롯들
        dets = []
        for pi in range(P):
            c = kp_center(kpts[ti, pi])
            if c is not None:
                dets.append((pi, c))
        used_tr = set()
        for pi, c in dets:
            best, bestd = None, 1e18
            for k, tr in enumerate(tracks):
                if k in used_tr:
                    continue
                if ti - tr["last_i"] > MAX_GAP:
                    continue
                d = math.hypot(c[0] - tr["last_c"][0], c[1] - tr["last_c"][1])
                # 끊긴 시간이 길수록 이동 허용치를 키운다
                lim = 120.0 + 40.0 * (ti - tr["last_i"])
                if d < bestd and d <= lim:
                    best, bestd = k, d
            if best is None:
                tracks.append({"frames": {ti: kpts[ti, pi]}, "last_c": c, "last_i": ti})
                used_tr.add(len(tracks) - 1)
            else:
                tracks[best]["frames"][ti] = kpts[ti, pi]
                tracks[best]["last_c"] = c
                tracks[best]["last_i"] = ti
                used_tr.add(best)
    return tracks


# ---------------- 59차원 피처 ----------------
def feat_of(kp, W, H):
    """검증된 59차원과 같은 순서. 박스는 유효 키포인트의 최소/최대로 대체(학습·추론 동일)."""
    v = kp[kp[:, 2] >= KP_TH]
    if len(v) == 0:
        return np.zeros(DIM, np.float32)
    x1, y1 = float(v[:, 0].min()), float(v[:, 1].min())
    x2, y2 = float(v[:, 0].max()), float(v[:, 1].max())
    w, h = max(x2 - x1, 1.0), max(y2 - y1, 1.0)
    conf = float(v[:, 2].mean())
    sh = [(kp[i][0], kp[i][1]) for i in (5, 6) if kp[i][2] >= KP_TH]
    hip = [(kp[i][0], kp[i][1]) for i in (11, 12) if kp[i][2] >= KP_TH]
    angle, neck_y = 90.0, 0.0
    if sh:
        neck_y = sum(p[1] for p in sh) / len(sh) / H
    if sh and hip:
        sx = sum(p[0] for p in sh) / len(sh); sy = sum(p[1] for p in sh) / len(sh)
        hx = sum(p[0] for p in hip) / len(hip); hy = sum(p[1] for p in hip) / len(hip)
        a = abs(math.degrees(math.atan2(hy - sy, hx - sx)))
        angle = min(a, 180 - a)
    base = [conf, (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, w / W, h / H,
            w / max(1.0, h), angle / 90.0, neck_y]
    kflat = []
    for i in range(17):
        kflat += [float(kp[i][0]) / W, float(kp[i][1]) / H, float(kp[i][2])]
    return np.array(base + kflat, np.float32)


def track_series(tr, t_all, W, H):
    """트랙을 0.5초 간격 시계열로. 트랙이 없는 시각은 0벡터(시간축 유지)."""
    idx = list(range(0, len(t_all), SUB))
    ts = t_all[idx]
    xs = np.zeros((len(idx), DIM), np.float32)
    present = np.zeros(len(idx), bool)
    for j, ti in enumerate(idx):
        # 0.5초 구간 안에 이 트랙이 잡힌 프레임이 있으면 사용
        for k in range(ti, min(ti + SUB, len(t_all))):
            if k in tr["frames"]:
                xs[j] = feat_of(tr["frames"][k], W, H)
                present[j] = True
                break
    return ts, xs, present


# ---------------- 모델(검증된 84.2 구조 그대로) ----------------
class SeqNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(DIM, 96, 5, padding=2), nn.ReLU(),
            nn.Conv1d(96, 96, 5, padding=2), nn.ReLU())
        self.gru = nn.GRU(96, 96, num_layers=2, batch_first=True, bidirectional=True)
        self.head = nn.Linear(192, 1)

    def forward(self, x):
        h = self.conv(x.transpose(1, 2)).transpose(1, 2)
        h, _ = self.gru(h)
        return self.head(h[:, -1]).squeeze(-1)


# ---------------- 데이터 준비 ----------------
def load_video(p):
    z = np.load(p)
    return z["t"], z["kpts"], z["wh"], float(z["gt_start"]), float(z["gt_dur"])


def tracks_of_video(p, min_present=WIN // 2):
    """영상 하나 → [(트랙시각, 트랙피처, 존재여부)] + 메타"""
    t_all, kpts, wh, gt, dur = load_video(p)
    if len(t_all) < MIN_LEN * SUB:
        return None
    W, H = int(wh[0]), int(wh[1])
    out = []
    for tr in build_tracks(kpts):
        if len(tr["frames"]) < min_present:
            continue
        ts, xs, pres = track_series(tr, t_all, W, H)
        if pres.sum() < min_present:
            continue
        out.append((ts, xs, pres))
    return out, gt, dur, p.stem


def windows(ts, xs, pres, gt, dur):
    """(창, 라벨) — 라벨: 정답구간과 50% 이상 겹치면 양성, 전혀 안 겹치면 음성"""
    res = []
    for e in range(WIN, len(ts)):
        seg = xs[e - WIN:e]
        if pres[e - WIN:e].sum() < WIN // 4:      # 거의 비어 있는 창은 버림
            continue
        t0, t1 = float(ts[e - WIN]), float(ts[e - 1])
        if gt < 0:
            res.append((seg, 0, t1)); continue
        ov = max(0.0, min(t1, gt + dur) - max(t0, gt))
        frac = ov / (t1 - t0 + 1e-6)
        if frac >= 0.5:
            res.append((seg, 1, t1))
        elif ov == 0:
            res.append((seg, 0, t1))
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(0); torch.manual_seed(0); np.random.seed(0)
    files = sorted(KPTS.glob("*.npz"))
    train_f = [p for p in files if not p.stem.startswith(DEPLOY_PREFIX)]
    dep_f = [p for p in files if p.stem.startswith(DEPLOY_PREFIX)]
    print(f"학습 {len(train_f)}편 · 배포 {len(dep_f)}편", flush=True)

    pos, neg = [], []
    ntr = 0
    for i, p in enumerate(train_f, 1):
        r = tracks_of_video(p)
        if not r:
            continue
        trs, gt, dur, stem = r
        ntr += len(trs)
        dur = max(dur, 5.0)
        # 정답 구간에 존재하는 트랙 중 대표 1개만 양성으로 (누가 쓰러졌는지 라벨이 없으므로)
        main_k, main_score = None, -1.0
        if gt >= 0:
            for k, (ts, xs, pres) in enumerate(trs):
                m = (ts >= gt) & (ts <= gt + dur) & pres
                if m.sum() == 0:
                    continue
                sc = float(xs[m][:, 0].mean()) * float(m.sum())   # 평균 신뢰도 × 존재 길이
                if sc > main_score:
                    main_k, main_score = k, sc
        for k, (ts, xs, pres) in enumerate(trs):
            for seg, y, _ in windows(ts, xs, pres, gt, dur):
                if y == 1 and k != main_k:
                    continue                      # 대표 아닌 트랙의 양성 후보는 버림(오라벨 방지)
                (pos if y else neg).append(seg)
        if i % 50 == 0:
            print(f"  학습 전처리 {i}/{len(train_f)} · 트랙 {ntr} · 양성창 {len(pos)}", flush=True)

    random.shuffle(neg)
    neg = neg[:len(pos) * 3]
    print(f"트랙 {ntr}개 · 창 양성 {len(pos)} 음성 {len(neg)}", flush=True)

    X = torch.tensor(np.stack(pos + neg), dtype=torch.float32)
    Y = torch.tensor([1.0] * len(pos) + [0.0] * len(neg))
    idx = torch.randperm(len(X)); X, Y = X[idx], Y[idx]

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = SeqNet().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.BCEWithLogitsLoss()
    B = 512
    for ep in range(12):
        net.train(); tot = 0.0
        for i in range(0, len(X), B):
            xb, yb = X[i:i + B].to(dev), Y[i:i + B].to(dev)
            opt.zero_grad(); loss = lossf(net(xb), yb); loss.backward(); opt.step()
            tot += float(loss) * len(xb)
        print(f"ep{ep + 1}: loss {tot / len(X):.4f}", flush=True)
    torch.save(net.state_dict(), OUT / "fall_track.pt")

    # ----- 배포 채점: 트랙별 독립 판정 → 가장 이른 돌파 시각 -----
    net.eval()
    per_video = {}
    with torch.no_grad():
        for p in dep_f:
            r = tracks_of_video(p)
            if not r:
                continue
            trs, gt, dur, stem = r
            curves = []
            for ts, xs, pres in trs:
                segs, tt = [], []
                for e in range(WIN, len(ts)):
                    if pres[e - WIN:e].sum() < WIN // 4:
                        continue
                    segs.append(xs[e - WIN:e]); tt.append(float(ts[e - 1]))
                if not segs:
                    continue
                lo = []
                for i in range(0, len(segs), B):
                    lo.append(net(torch.tensor(np.stack(segs[i:i + B]), dtype=torch.float32).to(dev)).cpu().numpy())
                curves.append((np.array(tt), np.concatenate(lo)))
            per_video[stem] = (curves, gt)
            print(f"  {stem}: 트랙 {len(curves)}", flush=True)

    np.savez_compressed(OUT / "deploy_track_logits.npz",
                        **{f"{k}__n": np.array([len(v[0])]) for k, v in per_video.items()},
                        **{f"{k}__gt": np.array([v[1]]) for k, v in per_video.items()},
                        **{f"{k}__t{i}": c[0] for k, v in per_video.items() for i, c in enumerate(v[0])},
                        **{f"{k}__z{i}": c[1] for k, v in per_video.items() for i, c in enumerate(v[0])})

    def score(th, need):
        """need = 임계 이상이 연속 need 창이어야 인정(잡음 억제)"""
        tp = fn = fp = 0
        detail = []
        for stem, (curves, gt) in per_video.items():
            onsets = []
            for tt, z in curves:
                run = 0
                for j in range(len(z)):
                    run = run + 1 if z[j] >= th else 0
                    if run >= need:
                        onsets.append(float(tt[j - need + 1])); break
            o = min(onsets) if onsets else None            # 처음 쓰러지는 사람
            ok = "미검"
            if o is None:
                fn += 1
            elif gt - BEFORE <= o <= gt + AFTER:
                tp += 1; ok = "정검"
            else:
                fp += 1; fn += 1; ok = "오검"
            detail.append((stem, gt, o, ok, len(curves)))
        r = tp / (tp + fn) if tp + fn else 0
        p_ = tp / (tp + fp) if tp + fp else 0
        return (round(2 * r * p_ / (r + p_) * 100, 2) if r + p_ else 0.0), tp, fn, fp, detail

    print("\n== 스펙 방식(사람별 독립 판정 → 처음 쓰러진 사람) 임계 스윕 ==", flush=True)
    res = []
    for th in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        for need in (1, 2, 3):
            f1, tp, fn, fp, det = score(th, need)
            res.append((f1, tp, fn, fp, th, need, det))
    res.sort(key=lambda x: -x[0])
    for r_ in res[:8]:
        print(f"  {r_[0]:6.2f} (정검 {r_[1]} 미검 {r_[2]} 오검 {r_[3]})  th{r_[4]} need{r_[5]}", flush=True)
    b = res[0]
    print(f"\n== 최고 설정 영상별 (th{b[4]} need{b[5]}) ==", flush=True)
    for stem, gt, o, ok, ntr_ in b[6]:
        print(f"  {stem:22s} GT {gt:6.0f}  SA {'-' if o is None else f'{o:7.1f}'}  {ok}  트랙{ntr_}", flush=True)
    print(f"\n기존 84.2(top-1 단일) 대비: {b[0]}", flush=True)


if __name__ == "__main__":
    main()

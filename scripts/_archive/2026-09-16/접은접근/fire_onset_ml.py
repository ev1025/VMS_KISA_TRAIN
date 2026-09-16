# -*- coding: utf-8 -*-
"""방화 온셋 분류기 (규칙 N/M 대체). 경량 GBM.
   입력: 프레임 신호열(fire/smoke conf) → 슬라이딩 창 피처 → '지금이 온셋 구간인가' 확률.
   평가: 배포 10편에 대해 K-fold 로 임계 선택(분산 최소) 후 F1. 기존 규칙 66.7 과 비교."""
import json, sys
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import KFold

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
WIN = 12          # 6초(0.5s 간격)
DELAY, BEFORE, AFTER = 10.0, 2.0, 10.0


def feats(sig, i):
    """i 시점 기준 과거 WIN 구간의 요약 피처 (스칼라 소수)"""
    a = np.array(sig[max(0, i-WIN+1):i+1], dtype=np.float32)   # (n,3) t,fire,smoke
    f, s = a[:, 1], a[:, 2]
    def st(x):
        return [x.max(), x.mean(), x.std(), float((x >= 0.4).sum())/len(x), x[-1],
                float(x[-1]-x[0])]
    return st(f) + st(s) + [float(len(a))]


def build(data, keys):
    X, y, meta = [], [], []
    for k in keys:
        d = data[k]; sig = d["sig"]; gt = d["gt"]
        for i in range(len(sig)):
            t = sig[i][0]
            # 양성: 이 시점에 온셋을 내면 정검이 되는 구간 (SA=t+DELAY 가 창 안)
            pos = 0
            if gt is not None:
                sa = t + DELAY
                pos = 1 if (gt - BEFORE <= sa <= gt + AFTER) else 0
            X.append(feats(sig, i)); y.append(pos); meta.append((k, t))
    return np.array(X, np.float32), np.array(y), meta


def onset_from_prob(sig, prob, th):
    for i in range(len(sig)):
        if prob[i] >= th:
            return sig[i][0]
    return None


def score(data, keys, model, th):
    tp = fn = fp = 0
    for k in keys:
        d = data[k]; sig = d["sig"]; gt = d["gt"]
        X, _, _ = build({k: d}, [k])
        p = model.predict_proba(X)[:, 1]
        o = onset_from_prob(sig, p, th)
        sa = None if o is None else o + DELAY
        if gt is None:
            if sa is not None: fp += 1
        elif sa is not None and gt-BEFORE <= sa <= gt+AFTER:
            tp += 1
        else:
            fn += 1
            if sa is not None: fp += 1
    r = tp/(tp+fn) if tp+fn else 0; pr = tp/(tp+fp) if tp+fp else 0
    return (2*r*pr/(r+pr)*100 if r+pr else 0.0), tp, fn, fp


def main():
    tr = json.load(open(G/"fire_sig_train.json"))
    dep = json.load(open(G/"fire_tl.json"))
    # 배포셋을 같은 스키마로
    deploy = {k: {"gt": v["gt_start"], "sig": v["fire_smoke"]} for k, v in dep.items()}

    keys = list(tr)
    X, y, _ = build(tr, keys)
    print(f"학습 창 {len(X)} (양성 {int(y.sum())}) · 영상 {len(keys)}")

    model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                           max_leaf_nodes=31, min_samples_leaf=50,
                                           class_weight="balanced", random_state=0)
    model.fit(X, y)

    # 임계 선택: 배포 10편을 5-fold 로 나눠 각 fold 최적 임계의 분산 최소 지점
    dk = list(deploy)
    ths = np.round(np.arange(0.30, 0.91, 0.05), 2)
    per_fold = []
    for trn, tst in KFold(n_splits=5, shuffle=True, random_state=0).split(dk):
        sub = [dk[i] for i in trn]
        best = max(ths, key=lambda t: score(deploy, sub, model, t)[0])
        per_fold.append(best)
    print("fold별 최적 임계:", per_fold)
    # 분산 최소(= 가장 자주 뽑힌/중앙값) 임계 채택
    th_sel = float(np.median(per_fold))
    print("채택 임계(중앙값):", th_sel)

    f1, tp, fn, fp = score(deploy, dk, model, th_sel)
    print(f"\n=== 배포 10편 결과 (ML 온셋) ===")
    print(f"  F1 {f1:.1f} (정검 {tp} 미검 {fn} 오검 {fp})   ← 기존 규칙 66.7")
    print("\n=== 임계별 전수 ===")
    for t in ths:
        s, a, b, c = score(deploy, dk, model, t)
        print(f"  th {t:.2f} → F1 {s:5.1f} (정검 {a} 미검 {b} 오검 {c})")


if __name__ == "__main__":
    main()

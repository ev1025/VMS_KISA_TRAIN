# -*- coding: utf-8 -*-
"""쓰러짐 분류기(SeqNet)를 장면 묶음 교차검증으로 다시 학습해, 330편의 '학습에 안 쓴' 곡선을 만든다.

왜 (2026-09-20)
    dumps/fall_seq_dev330 은 배포 SeqNet(fall_track.pt)의 학습 영상 330편 그대로다(feats/fall_kpts 와 330/330 겹침).
    그 위의 규칙 점수(0.755·4 = 92.92, 0.80·5 = 94.30)는 학습셋 점수라 일반화 척도가 아니다.
    장면 접두어(C045103 같은 24묶음)로 6겹을 나눠, 다른 겹으로 학습한 분류기가 낸 곡선(out-of-fold)을 편마다 남긴다.
    학습 레시피는 scripts/fall_track.py main 과 같다(양성 대표 트랙 1개, 음성 3배 표집, 12 epoch, AdamW 1e-3, 배치 512).

레시피 실험 축 (2026-09-20 오후, 제미나이 제안을 교차검증으로 검증)
    --ignore-pre S   정답 직전 S초 안에 끝나는 음성 창을 버린다. 채점 창이 정답 -2초부터라 그 구간 경보는 정검인데,
                     기본 라벨은 정답 전에 끝나는 창을 전부 음성으로 두어 '넘어지는 중' 을 음성으로 가르친다.
    --seeds K        겹마다 시드 K개를 학습해 로짓을 평균(앙상블).
    --hard-neg       겹의 학습 편을 장면으로 2분할해 반쪽으로 학습한 분류기가 나머지 반쪽에서 0.5 이상으로 본 음성 창을
                     '어려운 음성' 으로 모아 학습 음성에 3배로 더한다(빠진 겹은 건드리지 않아 누수 없음).
                     첫 결과(3배, 상한 3×양성): 오검 26 → 5 이지만 미검 54 → 75, 야간 84 → 68 로 과억제(87.34 → 86.44).
    --hard-weight/--hard-cap  그 세기를 조절한다(hn1 = 1배, 상한 1×양성 → 87.99, 오검 1, 미검 70, 야간 74).
    --hard-pre-only  어려운 음성을 사건 시작 전 창에서만 캔다. hn1 의 미검 증가가 "쓰러진 뒤 누워 있는 창(기본 라벨은 음성)을
                     어려운 음성으로 배워 낙상 자체를 억누른 탓" 인지 가른다. --ignore-post 는 그 창을 음성에서 아예 뺀다.
    --tag 이름       출력 폴더 접미사. 기본 레시피 결과(dumps/fall_seq_cv330_640)와 fall_sweep330.py 로 나란히 비교한다.

한계
    feats/fall_kpts 는 자세 640 으로 뽑은 키포인트다(배포는 1280). 절대 문턱은 어긋날 수 있어
    규칙의 상대 비교와 "학습셋 점수 vs 교차검증 점수" 차이(낙관 폭)를 보는 용도다.
    --kpts 로 다른 피처 폴더(예: feats/fall_kpts_1280)를 줄 수 있다.

출력
    dumps/fall_seq_cv330_<해상도>[_tag]/<편>.json   교차검증 곡선  {imgsz, fps, gt, fold, curves: [[(창끝 시각, 로짓)...], ...]}
    dumps/fall_seq_in330_<해상도>/<편>.json          배포 분류기의 학습셋 곡선(같은 형식, --no-insample 이면 생략)
    둘 다 scripts/fall_sweep330.py <폴더> [시작무시초] 로 훑는다.

사용
    CUDA_VISIBLE_DEVICES= .venv/bin/python scripts/fall_cv330.py [--folds 6] [--seed 0] [--threads 16]
                          [--ignore-pre 2] [--seeds 5] [--hard-neg] [--tag ig2] [--kpts feats/fall_kpts] [--imgsz 640]
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import fall_track as FT  # noqa: E402  (트랙·피처·창·SeqNet 을 그대로 쓴다)

FEAT_NOISE = 0.0            # 학습 창에 더하는 가우시안 잡음(정규화 단위). 0 = 없음. 픽셀 ±1 잡음에 둔감한 분류기 후보(2026-09-21)
DEV = torch.device("cpu")   # --device 로 바꾼다. CPU(oneDNN) 학습이 시작 직후 간헐 세그폴트를 내서 GPU 도 열어 둠(2026-09-20)


def prep(files):
    """편마다 트랙 시계열을 캐시. [(편, 정답, 지속, [(ts, xs, pres), ...]), ...]"""
    out = []
    for i, p in enumerate(files, 1):
        r = FT.tracks_of_video(p)
        if not r:
            print("  너무 짧아 건너뜀", p.stem, flush=True)
            continue
        trs, gt, dur, stem = r
        out.append((stem, gt, max(dur, 5.0), trs))
        if i % 50 == 0:
            print(f"  전처리 {i}/{len(files)}", flush=True)
    return out


def clip_windows(gt, dur, trs, ignore_pre=0.0, ignore_post=False):
    """fall_track.main 과 같은 라벨: 정답 구간 대표 트랙 1개만 양성, 구간 밖 창은 음성.
    ignore_pre > 0 이면 정답 직전 그 초 안에 끝나는 음성 창은 버린다.
    ignore_post 면 사건이 끝난 뒤(창 시작 > 정답 + 지속) 창도 버린다. 기본 라벨은 쓰러진 채 누워 있는 구간을 전부 음성으로 둔다.
    반환: pos, neg, neg_pre(음성 창이 사건 시작 전에 끝났는지 = 이른 오검 후보)"""
    pos, neg, neg_pre = [], [], []
    main_k, main_score = None, -1.0
    if gt >= 0:
        for k, (ts, xs, pres) in enumerate(trs):
            m = (ts >= gt) & (ts <= gt + dur) & pres
            if m.sum() == 0:
                continue
            sc = float(xs[m][:, 0].mean()) * float(m.sum())
            if sc > main_score:
                main_k, main_score = k, sc
    for k, (ts, xs, pres) in enumerate(trs):
        for seg, y, t1 in FT.windows(ts, xs, pres, gt, dur):
            if y == 1 and k != main_k:
                continue
            if y == 0 and gt >= 0 and ignore_pre > 0 and gt - ignore_pre <= t1 < gt:
                continue
            if y == 0 and gt >= 0 and ignore_post and t1 - (FT.WIN - 1) * 0.5 > gt + dur:
                continue
            if y:
                pos.append(seg)
            else:
                neg.append(seg); neg_pre.append(gt < 0 or t1 < gt)
    return pos, neg, neg_pre


def train(pos, neg, seed, extra_neg=None, epochs=12, B=512):
    """기본 레시피. extra_neg(어려운 음성)는 3배 표집 뒤에 그대로 덧붙인다."""
    random.seed(seed); torch.manual_seed(seed); np.random.seed(seed)
    neg = list(neg); random.shuffle(neg); neg = neg[:len(pos) * 3]
    extra = list(extra_neg or [])
    X = torch.tensor(np.stack(pos + neg + extra), dtype=torch.float32).to(DEV)
    Y = torch.tensor([1.0] * len(pos) + [0.0] * (len(neg) + len(extra))).to(DEV)
    idx = torch.randperm(len(X), device=DEV); X, Y = X[idx], Y[idx]
    net = FT.SeqNet().to(DEV)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.BCEWithLogitsLoss()
    tot = 0.0
    for _ep in range(epochs):
        net.train(); tot = 0.0
        for i in range(0, len(X), B):
            xb, yb = X[i:i + B], Y[i:i + B]
            if FEAT_NOISE:
                xb = xb + FEAT_NOISE * torch.randn_like(xb)
            opt.zero_grad(); loss = lossf(net(xb), yb); loss.backward(); opt.step()
            tot += float(loss.detach()) * len(xb)
    return net, len(pos), len(neg) + len(extra), tot / len(X)


@torch.no_grad()
def curves_of(nets, trs, B=512):
    """fall_track.main 의 배포 채점과 같은 방식: 트랙별 (창끝 시각, 로짓). nets 가 여럿이면 로짓 평균."""
    for n in nets:
        n.eval()
    curves = []
    for ts, xs, pres in trs:
        segs, tt = [], []
        for e in range(FT.WIN, len(ts)):
            if pres[e - FT.WIN:e].sum() < FT.WIN // 4:
                continue
            segs.append(xs[e - FT.WIN:e]); tt.append(float(ts[e - 1]))
        if not segs:
            continue
        X = torch.tensor(np.stack(segs), dtype=torch.float32).to(DEV)
        z = np.mean([np.concatenate([n(X[i:i + B]).cpu().numpy() for i in range(0, len(X), B)]) for n in nets], axis=0)
        curves.append([[round(t, 2), round(float(v), 3)] for t, v in zip(tt, z)])
    return curves


def mine_hard(tr_clips, win, seed, th=0.5, B=512, pre_only=False):
    """겹의 학습 편을 장면으로 2분할. 반쪽으로 학습한 분류기가 나머지 반쪽의 음성 창에 th 이상을 주면 어려운 음성.
    (학습은 grad 가 필요하니 no_grad 는 예측 부분에만 건다. 03:20 첫 실행은 함수 전체를 no_grad 로 감싸 죽었다.)"""
    scenes = sorted({c[0].split("_")[0] for c in tr_clips})
    halves = [set(scenes[0::2]), set(scenes[1::2])]
    hard = []
    for h in (0, 1):
        fit = [c for c in tr_clips if c[0].split("_")[0] in halves[1 - h]]
        mine = [c for c in tr_clips if c[0].split("_")[0] in halves[h]]
        net, *_ = train([w for c in fit for w in win[c[0]][0]], [w for c in fit for w in win[c[0]][1]], seed)
        net.eval()
        with torch.no_grad():
            for s, _gt, _dur, _trs in mine:
                negs = [w for w, pre in zip(win[s][1], win[s][2]) if pre] if pre_only else win[s][1]
                if not negs:
                    continue
                X = torch.tensor(np.stack(negs), dtype=torch.float32).to(DEV)
                p = torch.sigmoid(torch.cat([net(X[i:i + B]) for i in range(0, len(X), B)])).cpu().numpy()
                hard += [negs[i] for i in np.where(p >= th)[0]]
    return hard


def folds_by_scene(clips, k, seed):
    """장면 접두어(편 이름의 '_' 앞)를 통째로 한 겹에 넣는다. 큰 장면부터 가장 가벼운 겹에."""
    sizes = {}
    for s, *_ in clips:
        sizes[s.split("_")[0]] = sizes.get(s.split("_")[0], 0) + 1
    scenes = sorted(sizes); random.Random(seed).shuffle(scenes)
    fold_of, load = {}, [0] * k
    for sc in sorted(scenes, key=lambda s: -sizes[s]):
        j = load.index(min(load)); fold_of[sc] = j; load[j] += sizes[sc]
    return fold_of, load


def dump(out_dir, stem, gt, curves, imgsz, **extra):
    d = {"imgsz": imgsz, "fps": 10, "gt": gt, "curves": curves}
    d.update(extra)
    (out_dir / f"{stem}.json").write_text(json.dumps(d), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pt", default=str(V / "runs/fall_track/fall_track.pt"), help="배포 분류기(학습셋 곡선용)")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--kpts", default=str(FT.KPTS), help="키포인트 피처 폴더")
    ap.add_argument("--imgsz", type=int, default=640, help="그 피처를 뽑은 자세 해상도(출력 폴더 이름·json 에 적는다)")
    ap.add_argument("--ignore-pre", type=float, default=0.0)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--hard-neg", action="store_true")
    ap.add_argument("--hard-weight", type=int, default=3, help="어려운 음성 반복 횟수(기본 3)")
    ap.add_argument("--hard-cap", type=float, default=3.0, help="어려운 음성 총량 상한 = 양성 창 수 × 이 값(기본 3)")
    ap.add_argument("--hard-pre-only", action="store_true", help="어려운 음성을 사건 시작 전 창에서만 캔다(이른 오검만 겨냥)")
    ap.add_argument("--ignore-post", action="store_true", help="사건이 끝난 뒤(누워 있는) 창을 음성에서 뺀다")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-insample", action="store_true")
    ap.add_argument("--device", default="cpu", help="cpu 또는 cuda")
    a = ap.parse_args()
    global DEV
    DEV = torch.device(a.device)
    torch.set_num_threads(a.threads)
    suffix = f"_{a.tag}" if a.tag else ""
    out_cv = V / f"dumps/fall_seq_cv330_{a.imgsz}{suffix}"
    out_in = V / f"dumps/fall_seq_in330_{a.imgsz}"
    out_cv.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in Path(a.kpts).glob("*.npz") if not p.stem.startswith(FT.DEPLOY_PREFIX))
    print(f"학습 영상 {len(files)}편 · {a.folds}겹 장면 묶음 교차검증 · 피처 {a.kpts} (자세 {a.imgsz}) · "
          f"ignore_pre {a.ignore_pre} · ignore_post {a.ignore_post} · seeds {a.seeds} · hard_neg {a.hard_neg} "
          f"(w{a.hard_weight} cap{a.hard_cap} pre_only {a.hard_pre_only}) · device {a.device} → {out_cv}", flush=True)
    t0 = time.time(); clips = prep(files)
    print(f"전처리 {len(clips)}편 {time.time() - t0:.0f}s", flush=True)
    win = {s: clip_windows(gt, dur, trs, a.ignore_pre, a.ignore_post) for s, gt, dur, trs in clips}
    print(f"창 합계: 양성 {sum(len(v[0]) for v in win.values())} 음성 {sum(len(v[1]) for v in win.values())}", flush=True)

    # 1) 배포 분류기의 학습셋 곡선(같은 피처) = 낙관 폭을 재는 짝
    if not a.no_insample:
        out_in.mkdir(parents=True, exist_ok=True)
        net0 = FT.SeqNet(); net0.load_state_dict(torch.load(a.pt, map_location="cpu")); net0.to(DEV)
        t1 = time.time()
        for s, gt, _dur, trs in clips:
            dump(out_in, s, gt, curves_of([net0], trs), a.imgsz)
        print(f"학습셋 곡선 {len(clips)}편 → {out_in} {time.time() - t1:.0f}s", flush=True)

    # 2) 겹마다 다시 학습 → 빠진 겹의 곡선
    fold_of, load = folds_by_scene(clips, a.folds, a.seed)
    print("겹별 편수", load, flush=True)
    for f in range(a.folds):
        tr = [c for c in clips if fold_of[c[0].split("_")[0]] != f]
        te = [c for c in clips if fold_of[c[0].split("_")[0]] == f]
        pos = [w for c in tr for w in win[c[0]][0]]
        neg = [w for c in tr for w in win[c[0]][1]]
        t1 = time.time()
        hard = None
        if a.hard_neg:
            hard = mine_hard(tr, win, a.seed, pre_only=a.hard_pre_only)
            cap = int(len(pos) * a.hard_cap)
            hard = (hard * a.hard_weight)[:cap] if hard else []   # 반복 가중, 총량 상한(기본 3배·정규 음성과 같은 양)
        nets, info = [], None
        for k in range(a.seeds):
            net, npos, nneg, loss = train(pos, neg, a.seed + k, extra_neg=hard)
            nets.append(net); info = (npos, nneg, loss)
        for s, gt, _dur, trs in te:
            dump(out_cv, s, gt, curves_of(nets, trs), a.imgsz, fold=f)
        print(f"겹 {f}: 학습 {len(tr)}편(양성창 {info[0]} 음성창 {info[1]}"
              + (f", 어려운 음성 {len(hard)}" if hard is not None else "")
              + f", 마지막 loss {info[2]:.4f}, 시드 {a.seeds}) → 검증 {len(te)}편 {time.time() - t1:.0f}s", flush=True)
    print(f"끝. 훑기: .venv/bin/python scripts/fall_sweep330.py {out_cv}", flush=True)


if __name__ == "__main__":
    main()

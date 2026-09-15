# -*- coding: utf-8 -*-
"""여러 방화 모델의 신호를 프레임 단위로 합쳐 채점.

근거(실측): 같은 규칙에서 모델마다 놓치는 영상이 다르다.
  pilot(부분라벨 16에폭)  → C00_012, C00_195, C00_216 실패
  human_full(전체라벨 80에폭) → C00_146, C00_195, C00_216 실패
알람 단위로 합치면(둘 중 이른 것) 한쪽의 이른 오탐이 그대로 따라오므로,
신호 단위(같은 시각의 불/연기 신뢰도)로 합친 뒤 규칙을 적용한다.
합치는 방법 두 가지를 비교: 최대값(둘 중 하나만 봐도 인정) · 평균(둘 다 어느 정도 봐야 인정).
"""
import itertools
import json
import sys
from pathlib import Path

SP = Path(__file__).resolve().parents[1] / "dumps/score_tl"
BEFORE, AFTER, DELAY = 2.0, 10.0, 10.0


def load(tag):
    d = json.load(open(SP / f"{tag}.json"))
    return {k: ([tuple(r) for r in v["rows"]], v["gt"]) for k, v in d.items()}


def fuse(pers, how):
    """시각을 키로 맞춰 합침. 표본 시각은 모델마다 같다(같은 stride)."""
    stems = set.intersection(*[set(p) for p in pers])
    out = {}
    for s in stems:
        series = [dict((round(t, 2), (bf, bs)) for t, bf, bs in p[s][0]) for p in pers]
        ts = sorted(set.intersection(*[set(x) for x in series]))
        rows = []
        for t in ts:
            fs = [x[t][0] for x in series]
            ss = [x[t][1] for x in series]
            if how == "max":
                rows.append((t, max(fs), max(ss)))
            elif how == "mean":
                rows.append((t, sum(fs) / len(fs), sum(ss) / len(ss)))
            else:  # min = 둘 다 봐야 인정
                rows.append((t, min(fs), min(ss)))
        out[s] = (rows, pers[0][s][1])
    return out


def baseline(rows, sec=60.0):
    head = [(bf, bs) for t, bf, bs in rows if t <= sec]
    if not head:
        return 0.0, 0.0
    f = sorted(x[0] for x in head); s = sorted(x[1] for x in head)
    i = int(len(f) * 0.8)
    return f[min(i, len(f) - 1)], s[min(i, len(s) - 1)]


def onset(rows, fth, sdelta, win, hits, use_smoke):
    _, bs0 = baseline(rows)
    q = []
    for t, bf, bs in rows:
        hit = bf >= fth
        if use_smoke and not hit:
            hit = bs >= bs0 + sdelta and bs >= 0.3
        q.append((t, hit))
        if len(q) > win:
            q.pop(0)
        if sum(1 for _, h in q if h) >= hits:
            return next(t0 for t0, h in q if h)
    return None


def score(per, **kw):
    tp = fn = fp = 0; det = []
    for stem, (rows, gt) in sorted(per.items()):
        o = onset(rows, **kw)
        sa = None if o is None else o + DELAY
        if sa is None:
            v = "미검"; fn += 1
        elif gt - BEFORE <= sa <= gt + AFTER:
            v = "정검"; tp += 1
        else:
            v = "오검"; fp += 1; fn += 1
        det.append((stem, gt, sa, v))
    r = tp / (tp + fn) if tp + fn else 0
    p = tp / (tp + fp) if tp + fp else 0
    return (round(2 * r * p / (r + p) * 100, 2) if r + p else 0.0), tp, fn, fp, det


def sweep(per, label):
    res = []
    for fth in (0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30, 0.40, 0.50):
        for win, hits in ((2, 2), (3, 2), (4, 2), (4, 3), (6, 3), (6, 4), (8, 4), (8, 5), (12, 6)):
            for use_smoke, sdelta in [(False, 0.0)] + [(True, d) for d in (0.2, 0.3, 0.4, 0.5)]:
                f1, tp, fn, fp, det = score(per, fth=fth, sdelta=sdelta, win=win, hits=hits, use_smoke=use_smoke)
                res.append((f1, tp, fn, fp, fth, win, hits, use_smoke, sdelta, det))
    res.sort(key=lambda x: (-x[0], x[3]))
    b = res[0]
    top = [r for r in res if r[0] >= b[0] - 0.01]
    sm = f"연기+{b[8]:.1f}" if b[7] else "불만"
    miss = [s for s, g, sa, v in b[9] if v != "정검"]
    print(f"  {label:26s} {b[0]:6.2f} (정검{b[1]} 미검{b[2]} 오검{b[3]})  f{b[4]:.2f} {b[6]}/{b[5]} {sm}  "
          f"안정 {len(top)}/{len(res)}  실패={miss}")
    return b


def main():
    tags = sys.argv[1:] or ["pilot", "human_full"]
    pers = {t: load(t) for t in tags}
    print(f"모델 {len(tags)}개: {', '.join(tags)}\n")
    print("[단독]")
    for t in tags:
        sweep(pers[t], t)
    print("\n[신호 합치기]")
    best = None
    for n in range(2, len(tags) + 1):
        for combo in itertools.combinations(tags, n):
            for how in ("max", "mean", "min"):
                f = fuse([pers[t] for t in combo], how)
                b = sweep(f, f"{'+'.join(combo)} ({how})")
                if best is None or b[0] > best[0][0]:
                    best = (b, combo, how)
    if best:
        b, combo, how = best
        sm = f"연기+{b[8]:.1f}" if b[7] else "불만"
        print(f"\n[최고 조합] {'+'.join(combo)} ({how})  f{b[4]:.2f} {b[6]}/{b[5]} {sm} → {b[0]}")
        for stem, gt, sa, v in b[9]:
            print(f"  {stem:22s} GT {gt:5.0f}  SA {'-' if sa is None else f'{sa:7.1f}'}  {v}")


if __name__ == "__main__":
    main()

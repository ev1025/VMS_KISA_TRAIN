# -*- coding: utf-8 -*-
# 기준 확인: 고정 규칙(불 0.4 4회/6스텝)으로 재면 results/<실험>/score.txt 와 같은 값이 나온다.
#            그래서 이 파일의 스윕 결과를 신뢰할 수 있다.
"""방화 판정 규칙을 찾는다. 낙관(LOOCV)까지 같이 재서 고른다.

지금 쓰는 고정 규칙 4개는 전부 '짧은 창에 여러 번'(4회/6스텝) 꼴이라 두 편을 놓친다.
  C00_272_0003: 불이 117.5 118.0 [0.30] [0.30] 120.0 으로 가운데가 임계 아래라 4회를 못 채운다
                → 130.5 까지 밀려 SA 140.5, 유효창 [121,133] 밖
  C00_195_0001: 불이 113.5 에 한 번 뜨고 다음이 122.0 이라 어떤 연속 조건도 못 채운다
                → 미검 또는 125.0 으로 밀려 오검
둘 다 '창을 넓히고 요구 횟수를 줄이면' 풀리는 모양이다. 그 방향을 훑는다.

연기는 절대값이 아니라 앞 60초 기준선 대비 상승량으로 본다.
  C00_195_0001 은 안개영상이라 연기가 0초부터 420표본 중 419회 0.6 을 넘고 기준선이 0.972 다.
  절대값으로 보면 0초에 터진다. 상승량으로 보면 오르지 않으므로 발화하지 않는다.

SA 시각 = onset + 10초(KISA 규정). 정상검출 = GT-2 ~ GT+10.
"""
import json
import statistics as st
from collections import deque
from pathlib import Path

DELAY, BEFORE, AFTER = 10.0, 2.0, 10.0
V = Path(".")


def baseline(rows, sec=60.0):
    """앞 sec 초의 80퍼센타일. 이 영상이 '평소' 어느 정도로 보이는지."""
    head = [(f, s) for t, f, s in rows if t <= sec]
    if not head:
        return 0.0, 0.0
    fs = sorted(x[0] for x in head); ss = sorted(x[1] for x in head)
    i = int(len(fs) * 0.8)
    return fs[min(i, len(fs) - 1)], ss[min(i, len(ss) - 1)]


def onset(rows, fth, win, hits, sdelta):
    """불이 fth 이상이거나, 연기가 기준선+sdelta 이상(그리고 0.3 이상)인 표본이
    win 스텝 안에 hits 번 나오면, 그 창의 첫 충족 시각이 onset."""
    _, bs0 = baseline(rows)
    q = deque(maxlen=win)
    for t, bf, bs in rows:
        hit = bf >= fth
        if not hit and sdelta is not None:
            hit = bs >= bs0 + sdelta and bs >= 0.3
        q.append((t, hit))
        if sum(1 for _, h in q if h) >= hits:
            return next(t0 for t0, h in q if h)
    return None


def score(clips, fth, win, hits, sdelta):
    tp = fn = fp = 0
    det = []
    for stem, gt, rows in clips:
        o = onset(rows, fth, win, hits, sdelta)
        sa = None if o is None else o + DELAY
        if sa is None:
            v = "미검"; fn += 1
        elif gt - BEFORE <= sa <= gt + AFTER:
            v = "정검"; tp += 1
        else:
            v = "오검"; fn += 1; fp += 1
        det.append((stem, gt, sa, v))
    f1 = 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0
    return f1, tp, fn, fp, det


def load(tag):
    d = json.loads((V / "dumps/score_tl" / f"{tag}.json").read_text(encoding="utf-8"))
    return [(k, v["gt"], [tuple(r) for r in v["rows"]]) for k, v in sorted(d.items()) if v.get("gt") is not None]


# 원칙에 따라 좁힌 후보. 창을 넓히고 요구 횟수를 줄이는 방향 + 연기 상승량.
GRID = [(fth, win, hits, sd)
        for fth in (0.30, 0.35, 0.40, 0.45, 0.50)
        for win, hits in ((6, 3), (8, 3), (10, 3), (12, 3), (12, 4), (16, 3), (16, 4), (20, 3), (20, 4), (24, 4))
        for sd in (None, 0.2, 0.3, 0.4)]


def pick(rows_):
    """최고 점수 조합들 중 가운데(경계에서 먼 것)."""
    sc = [(score(rows_, *c)[0], c) for c in GRID]
    top = max(s for s, _ in sc)
    tied = [c for s, c in sc if s >= top - 1e-9]
    mid = [st.median([c[i] for c in tied]) if i != 3 else None for i in range(4)]
    return min(tied, key=lambda c: (abs(c[0] - mid[0]), abs(c[1] - mid[1]), abs(c[2] - mid[2]))), len(tied), top


if __name__ == "__main__":
    import sys
    tag = sys.argv[1] if len(sys.argv) > 1 else "fresh_48k_wildall_20260909"
    clips = load(tag)
    print(f"덤프 {tag} · {len(clips)}편 · 후보 {len(GRID)}조합\n")

    print("지금 쓰는 고정 규칙(참고)")
    for nm, c in (("fire만 0.4 4/6", (0.40, 6, 4, None)), ("결합+타일가정 3/5", (0.40, 5, 3, None))):
        f1, tp, fn, fp, _ = score(clips, *c)
        print(f"  {nm:20s} → {f1:6.2f}  (정검 {tp} 미검 {fn} 오검 {fp})")

    best, nt, top = pick(clips)
    f1, tp, fn, fp, det = score(clips, *best)
    sd = "연기없음" if best[3] is None else f"연기+{best[3]}"
    print(f"\n찾은 규칙  불 {best[0]} · {best[2]}회/{best[1]}스텝 · {sd}")
    print(f"  전수 {f1:.2f}  (정검 {tp} 미검 {fn} 오검 {fp}) · 동점 {nt}개")

    tp2 = fn2 = fp2 = 0
    picks = []
    for i, held in enumerate(clips):
        rest = clips[:i] + clips[i + 1:]
        c, n, _ = pick(rest)
        _, t1, n1, p1, d1 = score([held], *c)
        tp2 += t1; fn2 += n1; fp2 += p1
        picks.append((held[0], c, d1[0][3], n))
    l1 = 200.0 * tp2 / (2 * tp2 + fn2 + fp2) if tp2 else 0.0
    print(f"  LOOCV {l1:.2f}  (정검 {tp2} 미검 {fn2} 오검 {fp2}) · 낙관 {f1 - l1:+.2f}")

    print("\n편별 (찾은 규칙)")
    for stem, gt, sa, v in det:
        print(f"  {stem}: {v:4s} gt={gt} SA={sa} 창 [{gt-2}, {gt+10}]")
    print("\nLOOCV 편별 (그 편을 안 보고 고른 규칙)")
    for stem, c, v, n in picks:
        print(f"  {stem}: 불 {c[0]} {c[2]}회/{c[1]}스텝 {'연기없음' if c[3] is None else f'연기+{c[3]}'} (동점 {n}) → {v}")

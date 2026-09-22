# -*- coding: utf-8 -*-
"""방화 판정 규칙의 새 축을 훑는다. 덤프만 쓴다. 점수가 아니라 '여유' 를 본다.

왜 (2026-09-18)
    배포 앙상블은 10편 100.00 인데 200조합 중 100 을 내는 것이 3개뿐이고, 세 조합 모두 최소 여유가 0.5초다.
    경보 시각 ±1초를 밀면 90 으로 떨어진다(fire_margin.py). 만점이지만 봉우리다.

    구조를 보면 이유가 분명하다. 경보 = onset + 10초(KISA 규정)이고 정검 창이 [정답-2, 정답+10] 이므로
    onset 이 [정답-12, 정답] 안에 들어야 한다. 가운데는 정답-6초다.
      089_0001 : onset 206.5 = 정답보다 11.5초 이르다  -> 왼쪽 끝(너무 일찍 봄)
      195_0001 : onset 113.5 = 정답보다  0.5초 이르다  -> 오른쪽 끝(너무 늦게 봄)
    두 편이 반대 방향이라 문턱 하나로는 둘 다 못 넓힌다(올리면 089 는 좋아지고 195 가 깨진다).
    그래서 '한 번 반짝' 과 '드문드문 진짜' 를 가르는 축이 필요하다.

새 축
    sustain   onset 후보 시각 뒤 sustain 스텝 안에 한 번 더 신호가 있어야 인정(반짝 제거). 0 이면 끔.
    strong    창 안에 conf >= strong 인 표본이 한 번은 있어야 인정. 0 이면 끔.
    cusum     (conf - fth) 를 창 안에서 더한 값이 cusum 이상이면 인정(횟수 대신 누적 세기). 0 이면 끔.
    grace     불이 fth 를 못 넘어도 fth-grace 이상이면 '반쪽 표'(0.5회)로 센다. 0 이면 끔.

읽는 법
    점수가 같으면 최소 여유가 넓은 쪽이 시험장에서 안전하다. 흔들기(±1초)까지 100 이면 진짜 고원이다.

사용
    python scripts/fire_lab.py [덤프태그 ...]
"""
import itertools
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import fire_rule_search as F   # noqa: E402

F.V = V
DELAY, BEFORE, AFTER = F.DELAY, F.BEFORE, F.AFTER


def onset2(rows, fth, win, hits, sdelta, sustain=0, strong=0.0, cusum=0.0, grace=0.0):
    """fire_rule_search.onset 에 네 축을 더한 것. sustain·strong·cusum·grace 가 0 이면 원래와 같다."""
    _, bs0 = F.baseline(rows)
    q = deque(maxlen=win)
    for i, (t, bf, bs) in enumerate(rows):
        hit = bf >= fth
        if not hit and sdelta is not None:
            hit = bs >= bs0 + sdelta and bs >= 0.3
        half = (not hit) and grace > 0 and bf >= fth - grace      # 반쪽 표
        q.append((t, bf, 1.0 if hit else (0.5 if half else 0.0)))
        if sum(w for _, _, w in q) < hits:
            continue
        if strong and max(b for _, b, _ in q) < strong:
            continue                                              # 창 안에 센 표본이 없다
        if cusum and sum(max(0.0, b - fth) for _, b, _ in q) < cusum:
            continue                                              # 누적 세기가 모자라다
        t0 = next(tt for tt, _, w in q if w > 0)
        if sustain and not any(r[1] >= fth for r in rows[i + 1:i + 1 + sustain]):
            continue                                              # 뒤 sustain 스텝 안에 한 번 더 없으면 반짝으로 본다
        return t0
    return None


def detail(clips, kw):
    tp = fn = fp = 0
    marg, det = [], []
    for stem, gt, rows in clips:
        o = onset2(rows, **kw)
        sa = None if o is None else o + DELAY
        if sa is None:
            v = "미검"; fn += 1
        elif gt - BEFORE <= sa <= gt + AFTER:
            v = "정검"; tp += 1; marg.append(min(sa - (gt - BEFORE), (gt + AFTER) - sa))
        else:
            v = "오검"; fn += 1; fp += 1
        det.append((stem, gt, sa, v))
    f1 = 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0
    return dict(f1=f1, tp=tp, fn=fn, fp=fp, det=det, lo=min(marg) if marg else 0.0,
                avg=sum(marg) / len(marg) if marg else 0.0, tight=sum(1 for m in marg if m <= 1.0))


def shaken(clips, kw, d=1.0):
    out = []
    for sgn in (+1, -1):
        tp = fn = fp = 0
        for _s, gt, sa, _v in detail(clips, kw)["det"]:
            if sa is None:
                fn += 1; continue
            if gt - BEFORE <= sa + sgn * d <= gt + AFTER:
                tp += 1
            else:
                fn += 1; fp += 1
        out.append(200.0 * tp / (2 * tp + fn + fp) if tp else 0.0)
    return min(out)


GRID = dict(fth=[0.35, 0.40, 0.45], win=[12, 20, 24], hits=[3, 4], sdelta=[None],
            sustain=[0, 4, 8], strong=[0.0, 0.6, 0.75], cusum=[0.0, 0.3, 0.6], grace=[0.0, 0.1])
NOW = dict(fth=0.40, win=20, hits=3, sdelta=None, sustain=0, strong=0.0, cusum=0.0, grace=0.0)


def main():
    tags = sys.argv[1:] or ["_deploy"]
    keys = list(GRID)
    for tag in tags:
        clips = F.load(tag)
        now = detail(clips, NOW)
        res = [(detail(clips, dict(zip(keys, v))), dict(zip(keys, v))) for v in itertools.product(*GRID.values())]
        top = max(r["f1"] for r, _ in res)
        best = [(r, k) for r, k in res if r["f1"] >= top - 1e-9]
        best.sort(key=lambda x: (-x[0]["lo"], -x[0]["avg"], x[0]["tight"]))
        print("\n===== %s   %d편   (%d조합)" % (tag, len(clips), len(res)))
        print("  지금 규칙   %6.2f (%d/%d/%d)  최소여유 %.1fs 평균 %.1fs 아슬 %d편 · 흔들기 ±1s → %.2f"
              % (now["f1"], now["tp"], now["fn"], now["fp"], now["lo"], now["avg"], now["tight"], shaken(clips, NOW)))
        print("  최고 점수 %.2f 를 내는 조합 %d개 · 여유 넓은 순:" % (top, len(best)))
        for r, k in best[:8]:
            print("      불%.2f 창%2d %d회 지속%d 센%.2f 누적%.1f 반쪽%.1f : 최소여유 %.1fs 평균 %.1fs 아슬 %d편 · 흔들기 ±1s → %.2f"
                  % (k["fth"], k["win"], k["hits"], k["sustain"], k["strong"], k["cusum"], k["grace"],
                     r["lo"], r["avg"], r["tight"], shaken(clips, k)))
        b = best[0][0]
        print("      두 아슬 편의 경보: " + " · ".join("%s %s(여유 %.1f)" % (s.replace("C00_", ""), ("%.1f" % sa) if sa else "없음",
                                                                     min(sa - (gt - BEFORE), (gt + AFTER) - sa) if sa else 0)
                                                  for s, gt, sa, v in b["det"] if s.endswith(("089_0001", "195_0001"))))


if __name__ == "__main__":
    main()

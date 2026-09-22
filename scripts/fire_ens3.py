# -*- coding: utf-8 -*-
"""방화 앙상블 3벌 전수. 덤프만 쓴다. 점수가 아니라 '아슬한 편이 없는가' 로 고른다.

왜 (2026-09-18)
    배포 2벌 앙상블은 10편 100.00 이지만 089·195 두 편의 여유가 0.5초뿐이고, 규칙을 972조합 훑어도
    그 둘을 동시에 넓히는 규칙이 없다(fire_lab.py). 두 편이 서로 반대 방향이라 문턱 하나로는 못 민다.
      089 = 정답 11.5초 전에 봄(너무 이름) · 195 = 정답 0.5초 전에 겨우 봄(너무 늦음)
    규칙으로 안 되면 남는 길은 '195 를 더 일찍 보는 눈을 하나 더 얹는 것' 이다. 3벌을 전수로 본다.

주의
    앙상블은 표본마다 최고 신뢰도를 쓰므로 모델을 더할수록 경보가 빨라진다(089 쪽이 나빠질 수 있다).
    그래서 점수·아슬 편수·최소 여유를 같이 본다. 점수만 보면 100 이 널려 있어 고를 수가 없다.

사용
    python scripts/fire_ens3.py [--top 20] [--pool 24]     # pool = 단독 점수 상위 몇 개까지 조합에 넣을지
"""
import argparse
import itertools
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
_argv = sys.argv[1:]
sys.argv = [sys.argv[0]]          # fire_ens_all 은 import 될 때 argparse 를 돌린다. 내 인자와 부딪히지 않게 잠시 비운다
import fire_ens_all as E   # noqa: E402  (merge · judge · TL · DEPLOY · SKIP 을 그대로 쓴다)
sys.argv = [sys.argv[0]] + _argv
import kisa_items as K     # noqa: E402

C = K.ITEMS["fire"]


def detail(names):
    """점수 · 최소 여유 · 아슬 편수 · 못잡은 편."""
    d = E.merge(list(names))
    pairs, miss, marg = [], [], []
    for stem, e in sorted(d.items()):
        gt = e["gt"]; sa = E.judge(e["rows"])
        pairs.append(([{"start_s": gt, "desc": "F"}], [{"start_s": sa, "desc": "F"}] if sa is not None else []))
        if sa is None or not (gt - 2 <= sa <= gt + 10):
            miss.append(stem.replace("C00_", ""))
        else:
            marg.append(min(gt + 10 - sa, sa - (gt - 2)))
    return dict(score=K.score(pairs)["점수"], lo=min(marg) if marg else 0.0,
                tight=sum(1 for m in marg if m <= 1.0), miss=miss)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--pool", type=int, default=24)
    a = ap.parse_args()
    names = sorted(p.stem for p in E.TL.glob("*.json") if p.stem not in E.SKIP)
    singles = []
    for n in names:
        try:
            singles.append((detail((n,)), n))
        except Exception:
            pass
    singles.sort(key=lambda x: (-x[0]["score"], -x[0]["lo"], x[0]["tight"]))
    pool = [n for _r, n in singles[:a.pool]]
    for d in E.DEPLOY:                      # 배포 2벌은 점수가 낮아도 반드시 후보에 넣는다
        if d not in pool and d in names:
            pool.append(d)
    dep = detail(E.DEPLOY)
    print("덤프 %d개 · 조합 후보 %d개 · 3벌 %d가지 (규칙은 제출 도구 고정: 불 %.2f 창 %d %d회)"
          % (len(names), len(pool), len(list(itertools.combinations(pool, 3))), C["fire"], C["win"], C["hits"]))
    print("배포 2벌 : %6.2f · 최소여유 %.1fs · 아슬 %d편\n" % (dep["score"], dep["lo"], dep["tight"]))
    res = []
    for c in itertools.combinations(pool, 3):
        try:
            res.append((detail(c), c))
        except Exception:
            pass
    res.sort(key=lambda x: (-x[0]["score"], -x[0]["lo"], x[0]["tight"]))
    print("3벌 상위 %d (점수 → 최소여유 → 아슬 적은 순):" % a.top)
    for r, c in res[:a.top]:
        print("  %6.2f  최소여유 %.1fs  아슬 %d편  %s%s" % (r["score"], r["lo"], r["tight"], " + ".join(c),
                                                     ("  못잡음 " + ",".join(r["miss"])) if r["miss"] else ""))
    better = [(r, c) for r, c in res if r["score"] >= dep["score"] - 1e-9 and r["lo"] > dep["lo"] + 1e-9]
    print("\n배포와 같은 점수이면서 최소여유가 더 넓은 3벌: %d가지" % len(better))
    for r, c in better[:a.top]:
        print("  %6.2f  최소여유 %.1fs  아슬 %d편  %s" % (r["score"], r["lo"], r["tight"], " + ".join(c)))


if __name__ == "__main__":
    main()

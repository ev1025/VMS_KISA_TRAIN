# -*- coding: utf-8 -*-
"""규칙 훑기 공통: LOOCV(한 편 빼고 고르기). intr_rule4 · loiter_rule4 가 같이 쓴다.

왜 (docs/EXPERIMENTS.md 4.5 · 4.10)
    같은 채점셋으로 규칙을 고르고 그 채점셋 점수를 보고하면 낙관이 섞인다.
    한 편씩 빼고 나머지 29편으로 최고 조합을 고른 뒤, 뺀 편을 그 조합으로 채점해 모으면
    '규칙을 고르는 절차' 자체의 점수가 나온다. 전수 최고와의 차이가 낙관이다.
    보고할 때는 전수 · LOOCV · 동점 개수를 같이 적는다.
"""
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402


def pairs_score(gt, sa, clips, desc):
    """편 목록(clips)에 대한 KISA 점수. gt · sa 는 {편: 초 또는 None}."""
    pairs = [([{"start_s": gt[c], "desc": desc}] if gt.get(c) is not None else [],
              [{"start_s": sa[c], "desc": desc}] if sa.get(c) is not None else []) for c in clips]
    return K.score(pairs)["점수"]


def loocv(combos, gt, desc, now_kw=None):
    """combos = [(kw, {편: 경보시각}), ...]. 편마다 그 편을 뺀 나머지로 최고 조합을 고르고(동점이면 지금 규칙 우선,
    그다음 격자 순서), 뺀 편을 그 조합으로 채점한다. 모은 결과의 점수와 고른 조합 가짓수를 돌려준다."""
    clips = sorted(gt)
    full = {id(kw): pairs_score(gt, sa, clips, desc) for kw, sa in combos}
    held_sa, picks = {}, {}
    for c in clips:
        rest = [x for x in clips if x != c]
        best, best_kw, best_sa = None, None, None
        for kw, sa in combos:
            v = pairs_score(gt, sa, rest, desc)
            better = best is None or v > best + 1e-9 or (abs(v - best) <= 1e-9 and now_kw is not None and kw == now_kw and best_kw != now_kw)
            if better:
                best, best_kw, best_sa = v, kw, sa
        held_sa[c] = best_sa[c]
        picks[str(best_kw)] = picks.get(str(best_kw), 0) + 1
    return dict(score=pairs_score(gt, held_sa, clips, desc), n_picks=len(picks), picks=picks,
                full_best=max(full.values()) if full else 0)


def fmt_loocv(r):
    return "LOOCV %6.2f  (전수 최고 %.2f · 낙관 %+.2f · 편마다 고른 조합 %d가지)" % (
        r["score"], r["full_best"], r["full_best"] - r["score"], r["n_picks"])

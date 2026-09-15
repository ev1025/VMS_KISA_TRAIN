# -*- coding: utf-8 -*-
# 참고용: 신규칙의 원본 설계. 실제 계산은 score_kisa.py 와 kisa_items.py 안에 옮겨져 있다.
#         여기를 고쳐도 채점에 반영되지 않는다.
"""방화 온셋 규칙 재설계. 저장된 신호 시계열(pilot.json 등)로 추론 없이 즉시 스윕.

기존 규칙이 놓친 이유(실측):
  - C00_272: 진짜 화재 전에 고립된 불 스파이크(t=2,6,37...)가 있어 '첫 돌파'가 엉뚱한 데서 걸림
    → 짧은 창 안에서 2회 이상 연속으로 잡히는 것만 인정하면 고립 스파이크가 걸러진다
  - C00_012: 진짜 신호가 약함(0.16~0.18). 임계 0.2 로는 4초 늦어 창을 벗어남
    → 임계를 낮추되 위의 연속 조건으로 오탐을 막는다
  - C00_195/C00_216: 연기 신뢰도가 영상 내내 0.92 로 고정(변화 0). 절대값은 무의미
    → 자기 자신의 초반 기준선 대비 상승량으로 보면 이 두 편은 상승이 없어 여전히 안 잡힘(모델 한계)
"""
import json
import sys
from pathlib import Path

SP = Path(__file__).resolve().parents[1] / "dumps/score_tl"
BEFORE, AFTER, DELAY = 2.0, 10.0, 10.0
STEP = 0.5


def load(tag):
    d = json.load(open(SP / f"{tag}.json"))
    return {k: ([tuple(r) for r in v["rows"]], v["gt"]) for k, v in d.items()}


def baseline(rows, sec=60.0):
    """영상 앞부분에서 각 클래스의 평상시 값(80퍼센타일). 장면 자체를 연기로 오인하는 영상 대응."""
    head = [(bf, bs) for t, bf, bs in rows if t <= sec]
    if not head:
        return 0.0, 0.0
    f = sorted(x[0] for x in head)
    s = sorted(x[1] for x in head)
    i = int(len(f) * 0.8)
    return f[min(i, len(f) - 1)], s[min(i, len(s) - 1)]


def onset(rows, fth, sdelta, win, hits, use_smoke):
    """짧은 창 win 안에서 hits 회 이상 조건 충족 → 그 창의 첫 충족 시각.
       불: 절대 임계 fth. 연기: 자기 기준선 + sdelta (절대값이 아니라 상승량)."""
    bf0, bs0 = baseline(rows)
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
    tp = fn = fp = 0
    det = []
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


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    per = load(tag)
    print(f"===== {tag}: 영상 {len(per)}편 =====\n")

    print("[기준선] 영상 앞 60초의 평상시 값 (연기 오인 영상 확인)")
    for stem, (rows, gt) in sorted(per.items()):
        bf0, bs0 = baseline(rows)
        smax = max(bs for _, _, bs in rows)
        print(f"  {stem:22s} 불 기준 {bf0:.2f}  연기 기준 {bs0:.2f}  연기 최대 {smax:.2f}  상승여지 {smax - bs0:+.2f}")

    res = []
    for fth in (0.10, 0.14, 0.18, 0.22, 0.26, 0.30, 0.34, 0.40, 0.50):
        for win, hits in ((3, 2), (4, 2), (6, 3), (8, 4), (10, 5), (12, 5), (12, 7), (14, 6),
                          (16, 7), (16, 9), (20, 9), (20, 12)):   # 화재는 지속 사건 → 긴 창이 핵심
            for use_smoke, sdelta in [(False, 0.0)] + [(True, d) for d in (0.2, 0.3, 0.4, 0.5)]:
                f1, tp, fn, fp, det = score(per, fth=fth, sdelta=sdelta, win=win, hits=hits, use_smoke=use_smoke)
                res.append((f1, tp, fn, fp, fth, win, hits, use_smoke, sdelta, det))
    res.sort(key=lambda x: (-x[0], x[3], -x[4]))
    print("\n[규칙 스윕 상위 15]  (f=불임계, h/w=창 안 최소충족, 연기=기준선대비 상승량)")
    for r in res[:15]:
        sm = f"연기+{r[8]:.1f}" if r[7] else "불만"
        print(f"  {r[0]:6.2f} (정검 {r[1]} 미검 {r[2]} 오검 {r[3]})  f{r[4]:.2f} {r[6]}/{r[5]}  {sm}")

    b = res[0]
    sm = f"연기+{b[8]:.1f}" if b[7] else "불만"
    print(f"\n[최고 설정 영상별] f{b[4]:.2f} {b[6]}/{b[5]} {sm}")
    for stem, gt, sa, v in b[9]:
        print(f"  {stem:22s} GT {gt:5.0f}  SA {'-' if sa is None else f'{sa:7.1f}'}  {v}")

    # 안정성: 상위 설정들이 이웃 설정에서도 유지되는지 (10편뿐이라 과적합 위험)
    top = [r for r in res if r[0] >= b[0] - 0.01]
    print(f"\n[안정성] 최고점 {b[0]} 을 내는 설정 조합 {len(top)}개 / 전체 {len(res)}개")
    print(f"  불임계 범위 {min(r[4] for r in top):.2f}~{max(r[4] for r in top):.2f} · "
          f"연기사용 {sum(1 for r in top if r[7])}개 · 불만 {sum(1 for r in top if not r[7])}개")


if __name__ == "__main__":
    main()

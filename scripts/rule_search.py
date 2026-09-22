# -*- coding: utf-8 -*-
"""침입·배회 판정 규칙을 '손라벨 모델들에서 고르게 좋은가' 로 고른다. 덤프만 쓴다(추론 없음).

무엇을 기준으로 고르나 (2026-09-19 사용자 지시로 바뀜)
    이전 판은 '배포 모델 점수가 떨어지지 않을 것' 을 첫 조건으로 두었다. 그 조건은 뺐다.
    배포 모델은 의사라벨로 학습한 모델이라 기준이 될 수 없다. 손으로 라벨한 모델들끼리
    같은 규칙에서 고르게 좋은 점수가 나오는 것이 중요하다.

    그래서 목표(대상 = 손라벨 모델 덤프들):
      1) 대상들 중 최저 점수가 높을 것   (어느 손라벨 모델에 걸어도 버틴다)
      2) 대상들의 점수 폭이 좁을 것      (모델이 바뀌어도 점수가 출렁이지 않는다 = 규칙이 모델에 안 매였다)
      3) 평균 점수가 높을 것
      4) 창 여유가 넓을 것               (시험장에서 타이밍이 밀려도 버틴다)
    배포 모델은 참고(--ref)로만 찍는다. 점수가 떨어져도 탐색을 막지 않는다.

어떻게 찾나 (좌표 하강 = 한 축씩 바꿔 보기)
    지금 규칙에서 출발해 축을 하나씩 훑어 제일 나은 값으로 바꾸고, 더 좋아지지 않을 때까지 되풀이한다.
    전조합(축 13개면 수십만)을 다 돌 필요가 없고, 축을 늘려도 비용이 선형으로만 는다.
    같은 값이면 바꾸지 않는다(지금 값 우선). 끝나면 찾은 규칙 둘레를 한 축씩 흔들어 고원을 잰다.

축 (침입)  conf 꼭짓점 hold gap settle 시작물체무시(warm) 밖에서봤어야(out) 히스테리시스(lo) 중복정리 최소높이 트랙수명 구역여유 세로비
축 (배회)  conf 체류 끊김 대기 crowd 지연 구역여유 최소높이 트랙수명 세로비

사용
    python scripts/rule_search.py intrusion
    python scripts/rule_search.py loiter --dumps 손A=dumps/... 손B=dumps/... --ref 배포=dumps/...
"""
import argparse
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import intr_rule4 as I      # noqa: E402
import loiter_rule4 as L    # noqa: E402
import person_lab as P      # noqa: E402  (prefilter: 최소높이·트랙수명·구역여유·세로비)
import rule_common as RC    # noqa: E402

# 대상 = 손라벨 모델들(규칙을 여기에 맞춘다) · 참고 = 배포(의사라벨 모델, 찍기만 한다)
DEFAULT_DUMPS = {
    "intrusion": ["손32.6=dumps/intrusion_p1280hand_1280", "손10.8=dumps/intrusion_p1280ov2_1280"],
    "loiter": ["손32.6=dumps/loiter_p1280hand_bs1280", "손10.8=dumps/loiter_p1280ov2_bs1280"],
}
DEFAULT_REF = {"intrusion": ["배포=dumps/intrusion_tile_v3"], "loiter": ["배포=dumps/loiter_botsort_v2"]}
AXES = {
    "intrusion": dict(conf_th=[0.30, 0.35, 0.40, 0.45, 0.50], corners=[0, 2, 3], hold=[1, 2, 3],
                      gap=[2, 4, 6], settle=[12.0, 24.0, 36.0], warm_s=[0, 5, 10, 20], out_need=[0, 1],
                      lo=[0, 0.15, 0.20, 0.25], dedupe=[0, 0.5], minh=[0, 24, 40], age=[0, 4, 10],
                      margin=[0, 10, 20], ar=[0.0, 1.2]),
    "loiter": dict(conf_th=[0.30, 0.35, 0.40, 0.45], dwell=[4.0, 6.0, 8.0], gap=[6, 10, 14],
                   settle=[5.0, 8.0], crowd=[3, 5, 8], delay=[10.0], minh=[0, 24, 40], age=[0, 4, 10],
                   margin=[0, 10, 20, 40], ar=[0.0, 1.2]),
}
PRE = ("minh", "age", "margin", "ar")          # 판정기 앞에서 박스를 거르는 축


def make(item, dumps):
    """덤프마다 (이름, 편들, 구역, 정답, 신뢰도최대) 를 읽어 둔다."""
    M = I if item == "intrusion" else L
    out = []
    for spec in dumps:
        label, path = spec.split("=", 1)
        rows, poly, gt = M.load(path)
        if not rows:
            print("(덤프 없음, 건너뜀) " + path); continue
        zmax = {s: M.zone_max_conf(rows[s], poly[s]) for s in rows} if item == "intrusion" else None
        out.append(dict(label=label, rows=rows, poly=poly, gt=gt, zmax=zmax, cache={}))
    return M, out


def evaluate(M, item, d, kw):
    """규칙 하나를 덤프 하나에 적용. prefilter 결과는 덤프·축조합마다 한 번만 만든다."""
    pre = {k: kw[k] for k in PRE if k in kw}
    rule = {k: v for k, v in kw.items() if k not in PRE}
    key = tuple(sorted(pre.items()))

    def sa(s):
        if (s, key) not in d["cache"]:
            d["cache"][(s, key)] = P.prefilter(d["rows"][s], d["poly"][s], M.CFG["corners"], **pre)
        return M.sa_entry(d["cache"][(s, key)], d["poly"][s], **rule)

    if item == "intrusion":
        return M.run(d["rows"], d["poly"], d["gt"], d["zmax"], lambda s: sa(s))
    return M.run(d["rows"], d["poly"], d["gt"], lambda s: sa(s))


def objective(M, item, data, kw):
    """(최저 점수, 평균 점수, -점수 폭, 최소 여유). 큰 것이 좋다. 대상(손라벨) 덤프만 본다.

    순서에 뜻이 있다. 최저가 먼저인 이유는 '어느 모델에 걸어도 버티는가' 가 첫 조건이기 때문이고,
    평균이 폭보다 먼저인 이유는 한 모델만 더 좋아지는 변화(다른 모델은 그대로)를 버리지 않기 위해서다.
    폭은 같은 최저·평균일 때만 가른다(2026-09-19: 폭을 먼저 뒀더니 94.74/91.23 을 버리고 91.23/91.23 을 골랐다)."""
    rs = [evaluate(M, item, d, kw) for d in data]
    sc = [r["score"] for r in rs]
    return (round(min(sc), 2), round(sum(sc) / len(sc), 2), -round(max(sc) - min(sc), 2),
            round(min(r["edge"] for r in rs), 1)), rs


def show(M, label, r):
    print("   %-8s %s" % (label, M.fmt(r)))
    print("            못잡음 %s" % r["miss"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("item", choices=["intrusion", "loiter"])
    ap.add_argument("--dumps", nargs="*", default=None, help="대상 라벨=덤프폴더 (규칙을 여기에 맞춘다)")
    ap.add_argument("--ref", nargs="*", default=None, help="참고 라벨=덤프폴더 (점수만 찍는다)")
    ap.add_argument("--rounds", type=int, default=4)
    a = ap.parse_args()
    M, data = make(a.item, a.dumps or DEFAULT_DUMPS[a.item])
    _, ref = make(a.item, a.ref if a.ref is not None else DEFAULT_REF[a.item])
    if not data:
        return 1
    axes = AXES[a.item]
    now = dict(M.NOW)
    for k in PRE:
        now.setdefault(k, 0.0 if k == "ar" else 0)
    print("== %s · 대상(손라벨) %d벌 · 참고 %d벌 · 축 %d개 · 좌표 하강 %d바퀴"
          % (a.item, len(data), len(ref), len(axes), a.rounds))
    print("   목표: 대상들 최저 점수 최대 → 평균 최대 → 점수 폭 최소 → 여유 최대 (배포 점수는 제약 아님)")
    print("   지금 규칙")
    for d in data + ref:
        show(M, d["label"], evaluate(M, a.item, d, now))

    cur = dict(now)
    best, best_rs = objective(M, a.item, data, cur)
    print("\n   탐색")
    for rnd in range(a.rounds):
        moved = False
        for ax, vals in axes.items():
            if ax not in cur:
                continue
            for v in vals:
                if v == cur[ax]:
                    continue
                sc, rs = objective(M, a.item, data, dict(cur, **{ax: v}))
                if sc > best:
                    print("   [%d바퀴] %s %s -> %s : 최저 %.2f · 평균 %.2f · 폭 %.2f · 여유 %.1fs"
                          % (rnd + 1, ax, cur[ax], v, sc[0], sc[1], -sc[2], sc[3]))
                    best, best_rs, cur, moved = sc, rs, dict(cur, **{ax: v}), True
        if not moved:
            break
    # 되돌리기 한 바퀴: 바꾼 축을 하나씩 원래 값으로 돌려 보고, 목표가 나빠지지 않으면 돌린 채로 둔다.
    # 좌표 하강은 훑는 순서에 끌려가 필요 없는 변경을 달고 온다(2026-09-19: conf 0.40->0.30 이 그랬다.
    # 나중에 끊김·구역여유가 들어오면서 conf 변경은 값어치가 없어졌는데도 남아 있었다).
    for ax in [k for k in cur if k in axes and cur[k] != now.get(k)]:
        sc, rs = objective(M, a.item, data, dict(cur, **{ax: now[ax]}))
        if sc >= best:
            print("   [되돌림] %s %s -> %s (목표가 안 나빠진다)" % (ax, cur[ax], now[ax]))
            best, best_rs, cur = sc, rs, dict(cur, **{ax: now[ax]})
    # 줄이기 한 바퀴: 남은 변경을 '지금 값에 더 가까운 값' 으로 낮춰 본다(구역여유 40px 대신 10px 처럼).
    for ax in [k for k in cur if k in axes and cur[k] != now.get(k)]:
        for v in sorted(axes[ax], key=lambda x: abs(x - now[ax]) if isinstance(x, (int, float)) else 0):
            if v == cur[ax]:
                break                                   # 지금 값이 이미 제일 가깝다
            sc, rs = objective(M, a.item, data, dict(cur, **{ax: v}))
            if sc >= best:
                print("   [줄임] %s %s -> %s (목표가 안 나빠진다)" % (ax, cur[ax], v))
                best, best_rs, cur = sc, rs, dict(cur, **{ax: v})
                break
    changed = {k: v for k, v in cur.items() if v != now.get(k)}
    print("\n찾은 규칙: " + (" ".join("%s=%s" % (k, v) for k, v in changed.items()) if changed else "(지금 규칙에서 안 움직임)"))
    for d, r in zip(data, best_rs):
        show(M, d["label"], r)
    for d in ref:
        show(M, d["label"] + "(참고)", evaluate(M, a.item, d, cur))
    flat = tot = 0                     # 고원: 축 하나만 흔들어 같은 최저 점수를 유지하는 값의 비율
    for ax, vals in axes.items():
        if ax not in cur:
            continue
        for v in vals:
            if v == cur[ax]:
                continue
            tot += 1
            sc, _ = objective(M, a.item, data, dict(cur, **{ax: v}))
            flat += sc[0] >= best[0] - 1e-9
    print("   고원: 한 축을 흔든 %d가지 중 %d가지가 같은 최저 점수를 유지(%.0f%%)" % (tot, flat, 100.0 * flat / max(1, tot)))
    for d in data:                     # 모델마다 LOOCV: 지금 규칙 vs 찾은 규칙 두 개만 후보로 둔 절차
        cand = [(k, {s: evaluate(M, a.item, d, k)["sa"][s] for s in d["rows"]}) for k in (now, cur)]
        lo = RC.loocv(cand, {s: g for s, g in d["gt"].items() if g is not None},
                      "I" if a.item == "intrusion" else "L", now)
        print("   %-8s %s" % (d["label"], RC.fmt_loocv(lo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

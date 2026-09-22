# -*- coding: utf-8 -*-
"""침입·배회 판정 규칙의 새 축을 훑는다. 덤프만 쓴다. 판정기는 제출 도구 것을 그대로 쓴다(감싸기).

왜 (2026-09-18, "손라벨용 여러가지 규칙 더 찾아보자")
    지금까지 훑은 축: conf·꼭짓점·hold·gap·settle·시작물체 무시·밖에서 봤어야·히스테리시스·중복정리
                      (침입) / conf·체류·끊김·대기·delay·crowd·발끝여유 (배회).
    아직 안 본 축이 네 개 남았다. 모두 '손라벨 모델이 배포 모델보다 많이·멀리 본다' 는 성질에서 나온다.

새 축 (침입·배회 공통으로 박스를 걸러 넣는다)
    minh    박스 높이가 minh 픽셀보다 작으면 버린다. 먼 사람·잡음 박스를 뺀다. 0 이면 끔.
    age     그 트랙이 영상 전체에서 age 표본 미만으로만 보였으면 버린다(반짝 트랙). 0 이면 끔.
    margin  발끝이 구역 경계에서 margin 픽셀 안쪽에 있어야 '안' 으로 친다. 0 이면 끔.
    ar      박스의 세로/가로 비가 ar 미만이면 버린다(사람은 세로로 길다). 0 이면 끔.

읽는 법 (docs/EXPERIMENTS.md 4.5 · 4.10)
    지금 규칙 = 대표값 · 최고 = 상한(같은 30편으로 골랐으니 낙관 포함) · LOOCV = 한 편 빼고 고른 절차의 점수
    고원(같은 점수 조합 수)이 5 미만이면 봉우리라 믿지 않는다.

사용
    python scripts/person_lab.py intrusion [덤프 ...]
    python scripts/person_lab.py loiter    [덤프 ...]
"""
import itertools
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K      # noqa: E402
import intr_rule4 as I      # noqa: E402
import loiter_rule4 as L    # noqa: E402
import rule_common as RC    # noqa: E402


def track_life(rows):
    """트랙마다 영상 전체에서 몇 표본 보였나."""
    n = {}
    for r in rows:
        for b in r["boxes"]:
            n[b[0]] = n.get(b[0], 0) + 1
    return n


def prefilter(rows, poly, corners, minh=0, age=0, margin=0, ar=0.0):
    """박스를 걸러 새 rows 를 만든다. 넷 다 0 이면 원본 그대로 돌려준다(자기검사용)."""
    if not (minh or age or margin or ar):
        return rows
    life = track_life(rows) if age else {}
    out = []
    for r in rows:
        keep = []
        for b in r["boxes"]:
            pid, _conf, x1, y1, x2, y2 = b
            h, w = y2 - y1, max(1e-6, x2 - x1)
            if minh and h < minh:
                continue
            if ar and h / w < ar:
                continue
            if age and life.get(pid, 0) < age:
                continue
            if margin and K.entered((x1, y1, x2, y2), poly, corners) and not L.foot_inside((x1, y1, x2, y2), poly, margin):
                continue                                   # 경계에 걸친 발끝은 구역 밖으로 친다
            keep.append(b)
        out.append({"t": r["t"], "boxes": keep})
    return out


GRID = dict(minh=[0, 24, 40, 60], age=[0, 4, 10], margin=[0, 10, 20], ar=[0.0, 1.2])


def main():
    item = sys.argv[1] if len(sys.argv) > 1 else "intrusion"
    M = I if item == "intrusion" else L
    corners = M.CFG["corners"]
    dumps = sys.argv[2:] or ([
        "dumps/intrusion_tile_v3", "dumps/intrusion_p1280hand_1280", "dumps/intrusion_p1280ov2_1280"]
        if item == "intrusion" else
        ["dumps/loiter_botsort_v2", "dumps/loiter_p1280hand_bs1280", "dumps/loiter_p1280ov2_bs1280"])
    keys = list(GRID)
    for dump in dumps:
        rows, poly, gt = M.load(dump)
        if not rows:
            print("\n===== %s : 덤프 없음" % dump); continue
        pre = {}                                            # (편, 축조합) -> 걸러진 rows. 조합마다 다시 만들지 않게
        def sa(s, kw):
            key = (s, tuple(sorted(kw.items())))
            if key not in pre:
                pre[key] = prefilter(rows[s], poly[s], corners, **kw)
            return M.sa_entry(pre[key], poly[s], **M.NOW)

        zmax = {s: M.zone_max_conf(rows[s], poly[s]) for s in rows} if item == "intrusion" else None

        def run(fn):
            """침입 run() 은 zmax 인자가 하나 더 있다(신뢰도 간격 지표)."""
            return M.run(rows, poly, gt, zmax, fn) if item == "intrusion" else M.run(rows, poly, gt, fn)

        zero = dict.fromkeys(keys, 0)
        zero["ar"] = 0.0
        base = run(lambda s: sa(s, zero))
        now = run(lambda s: M.sa_entry(rows[s], poly[s], **M.NOW))
        if abs(base["score"] - now["score"]) > 1e-9:
            print("\n===== %s : 자기검사 실패(걸러내기 끈 값이 지금 규칙과 다르다 %.2f vs %.2f)" % (dump, base["score"], now["score"])); continue
        res = [(run(lambda s, kw=dict(zip(keys, v)): sa(s, kw)), dict(zip(keys, v))) for v in itertools.product(*GRID.values())]
        res.sort(key=lambda x: (-x[0]["score"], -x[0]["edge"]))
        top = res[0][0]["score"]
        flat = sum(1 for r, _ in res if r["score"] >= top - 0.01)
        print("\n===== %s   %d편   (%d조합 · 자기검사 통과)" % (dump, len(rows), len(res)))
        print("  지금 규칙   %s" % M.fmt(now))
        print("  최고        %s  고원 %d%s" % (M.fmt(res[0][0]), flat, "" if flat >= 5 else "  <- 봉우리"))
        print("              설정   %s" % res[0][1])
        print("              못잡음 %s" % res[0][0]["miss"])
        lo = RC.loocv([(kw, r["sa"]) for r, kw in res], {s: g for s, g in gt.items() if g is not None},
                      "I" if item == "intrusion" else "L", zero)
        print("  %s" % RC.fmt_loocv(lo))
        for ax in keys:
            line = "  %-7s:" % ax
            for v in GRID[ax]:
                r = next(r for r, kw in res if kw == dict(zero, **{ax: v}))
                line += "  %s=%-4s %6.2f(%2d/%d/%d)" % (ax, v, r["score"], r["tp"], r["fn"], r["fp"])
            print(line)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""침입 규칙의 넓은 축(settle · hold 3~4 · gap 3~6 · corners 2)을 훑는다. intr_rule4 의 판정 감싸기를 그대로 쓴다.

왜 (2026-09-18)
    intr_rule4 는 conf·corners·hold·gap 을 배포값 근처에서만 훑었다("이게 최선이냐" 는 질문에 답하려면 넓은 축도 봐야 한다).
    settle(마지막 진입 뒤 확정까지 기다리는 초, 배포 24)은 한 번도 안 훑었다.

사용
    python scripts/intr_wide.py [덤프폴더 ...]
"""
import itertools
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import intr_rule4 as R      # noqa: E402
import rule_common as RC    # noqa: E402

GRID = dict(conf_th=[0.35, 0.40, 0.45], corners=[2, 3], hold=[1, 2, 3, 4], gap=[2, 3, 4, 6], warm_s=[0, 5],
            out_need=[0], lo=[0, 0.15], win_s=[3.0], dedupe=[0], settle=[12.0, 24.0, 36.0])


def main():
    dumps = sys.argv[1:] or ["dumps/intrusion_tile_v3", "dumps/intrusion_p1280hand_1280", "dumps/intrusion_p1280ov2_1280"]
    keys = list(GRID)
    for dump in dumps:
        rows, poly, gt = R.load(dump)
        if not rows:
            print("\n===== %s : 덤프 없음" % dump); continue
        zmax = {s: R.zone_max_conf(rows[s], poly[s]) for s in rows}
        bad = [s for s in rows if R.sa_now(rows[s], poly[s]) != R.sa_entry(rows[s], poly[s], **R.NOW)]
        if bad:
            print("\n===== %s : 자기검사 실패 %s" % (dump, bad)); continue
        res = [(R.run(rows, poly, gt, zmax, lambda s, kw=dict(zip(keys, v)): R.sa_entry(rows[s], poly[s], **kw)), dict(zip(keys, v)))
               for v in itertools.product(*GRID.values())]
        now = R.run(rows, poly, gt, zmax, lambda s: R.sa_entry(rows[s], poly[s], **R.NOW))
        res.sort(key=lambda x: (-x[0]["score"], -x[0]["edge"], -(x[0]["gap"] if x[0]["gap"] is not None else -9)))
        top = res[0][0]["score"]
        flat = sum(1 for r, _ in res if r["score"] >= top - 0.01)
        print("\n===== %s   %d편   (%d조합 · 넓은 축)" % (dump, len(rows), len(res)))
        print("  지금 규칙   %s" % R.fmt(now))
        print("  최고        %s  고원 %d%s" % (R.fmt(res[0][0]), flat, "" if flat >= 5 else "  <- 봉우리"))
        print("              못잡음 %s" % res[0][0]["miss"])
        print("              설정   %s" % {k: v for k, v in res[0][1].items() if k not in ("out_need", "win_s", "dedupe")})
        lo = RC.loocv([(kw, r["sa"]) for r, kw in res], {s: g for s, g in gt.items() if g is not None}, "I", None)
        print("  %s" % RC.fmt_loocv(lo))
        print("  settle × hold (conf 0.45 · corners 3 · gap 2 · warm 0 · lo 0 = 지금 값 고정):")
        for st in GRID["settle"]:
            line = "    settle %2.0fs :" % st
            for h in GRID["hold"]:
                r = next(r for r, kw in res if kw == dict(R.NOW, settle=st, hold=h))
                line += "  hold%d %6.2f(%2d/%d/%d)" % (h, r["score"], r["tp"], r["fn"], r["fp"])
            print(line)
        print("  gap (지금 값 고정):" + "".join("  gap%d %6.2f" % (g, next(r for r, kw in res if kw == dict(R.NOW, gap=g))["score"]) for g in GRID["gap"]))
        print("  corners 2 (지금 값 고정): %6.2f" % next(r for r, kw in res if kw == dict(R.NOW, corners=2))["score"])


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""방화가 '안정' 인지 본다: 100점이 넓은 고원 위인가, 아슬아슬한 봉우리인가. 덤프만 쓴다.

왜 (2026-09-18, "방화 이제 안정화됐니")
    배포 앙상블은 10편에서 100.00 인데 BASELINE.json 에 두 가지 경고가 붙어 있다.
      (1) LOOCV 80.00 = 낙관 +20  (2) 089·195 편은 창 여유가 0.5초
    점수만 보면 만점이라 더 볼 것이 없어 보인다. 실제로 봐야 하는 것은 '흔들었을 때 버티나' 다.

무엇을 재나 (한 조합마다)
    점수        지금 채점 방식 그대로
    최소 여유   정검 편들이 창 경계까지 남긴 최소 초. 시험장에서 타이밍이 이만큼 밀리면 깨진다.
    평균 여유   편들의 평균
    아슬 편수   여유 1.0초 이하인 편 수
    LOOCV      한 편 빼고 고른 절차의 점수(낙관 크기)
    시각 흔들기 모든 경보 시각을 ±d 초 밀었을 때도 100 인가(d = 0.5 · 1.0 · 2.0)

사용
    python scripts/fire_margin.py [덤프태그 ...]     (기본 _deploy = 배포 앙상블)
"""
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
import fire_rule_search as F   # noqa: E402  (onset · score · load · GRID 를 그대로 쓴다)

F.V = V                         # fire_rule_search 는 상대경로 기준이라 루트를 박아 준다
NOW = (0.40, 20, 3, None)       # 배포 규칙: 불 0.40 · 창 20스텝 · 3회 · 연기 안 씀


def detail(clips, combo):
    """조합 하나의 점수·여유·아슬 편수. 여유 = 창 경계까지 남은 초."""
    f1, tp, fn, fp, det = F.score(clips, *combo)
    marg = []
    for _stem, gt, sa, v in det:
        if v == "정검":
            marg.append(min(sa - (gt - F.BEFORE), (gt + F.AFTER) - sa))
    return dict(f1=f1, tp=tp, fn=fn, fp=fp, det=det,
                lo=min(marg) if marg else 0.0, avg=sum(marg) / len(marg) if marg else 0.0,
                tight=sum(1 for m in marg if m <= 1.0))


def shifted(clips, combo, d):
    """모든 경보 시각을 +d·-d 초 밀었을 때의 점수 중 나쁜 쪽(시험장 타이밍 흔들림 모사)."""
    out = []
    for sgn in (+1, -1):
        tp = fn = fp = 0
        for _stem, gt, sa, _v in F.score(clips, *combo)[4]:
            if sa is None:
                fn += 1; continue
            s = sa + sgn * d
            if gt - F.BEFORE <= s <= gt + F.AFTER:
                tp += 1
            else:
                fn += 1; fp += 1
        out.append(200.0 * tp / (2 * tp + fn + fp) if tp else 0.0)
    return min(out)


def main():
    tags = sys.argv[1:] or ["_deploy"]
    for tag in tags:
        clips = F.load(tag)
        now = detail(clips, NOW)
        res = [(detail(clips, c), c) for c in F.GRID]
        top = max(r["f1"] for r, _ in res)
        best = [(r, c) for r, c in res if r["f1"] >= top - 1e-9]
        best.sort(key=lambda x: (-x[0]["lo"], -x[0]["avg"], x[0]["tight"]))
        lo = F.__dict__.get("pick")
        print("\n===== %s   %d편   (%d조합)" % (tag, len(clips), len(F.GRID)))
        print("  지금 규칙(불 %.2f 창 %d %d회)  %6.2f (%d/%d/%d)  최소여유 %.1fs · 평균여유 %.1fs · 아슬(<=1s) %d편"
              % (NOW[0], NOW[1], NOW[2], now["f1"], now["tp"], now["fn"], now["fp"], now["lo"], now["avg"], now["tight"]))
        for stem, gt, sa, v in now["det"]:
            m = "-" if sa is None else "%.1f" % min(sa - (gt - F.BEFORE), (gt + F.AFTER) - sa)
            print("      %s  정답 %5.1f  경보 %s  %s  여유 %s" % (stem.replace("C00_", ""), gt, ("%.1f" % sa) if sa else "없음", v, m))
        print("  시각 흔들기: ±0.5s → %.2f · ±1.0s → %.2f · ±2.0s → %.2f"
              % (shifted(clips, NOW, 0.5), shifted(clips, NOW, 1.0), shifted(clips, NOW, 2.0)))
        print("  같은 점수(%.2f) 조합 %d개 중 여유가 넓은 순:" % (top, len(best)))
        for r, c in best[:6]:
            print("      불 %.2f 창 %2d %d회 연기Δ %-4s : 최소여유 %.1fs 평균 %.1fs 아슬 %d편 · 흔들기 ±1.0s → %.2f"
                  % (c[0], c[1], c[2], c[3], r["lo"], r["avg"], r["tight"], shifted(clips, c, 1.0)))
        if best[0][1] != NOW:
            print("      → 지금 규칙보다 최소여유가 %.1fs 넓은 조합이 있다" % (best[0][0]["lo"] - now["lo"]))


if __name__ == "__main__":
    main()

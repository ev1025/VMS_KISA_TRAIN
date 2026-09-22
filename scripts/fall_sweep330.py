# -*- coding: utf-8 -*-
"""쓰러짐 규칙(문턱 th · 연속 창 need)을 편 단위 곡선 덤프로 훑는다. 채점 10편으로 고른 값이 고원 위인지 본다.

왜 (2026-09-20)
    배포 쓰러짐 100 은 10편 근거다. 10편이면 한 편이 5점이고, 문턱 0.755·4회는 그 10편에 맞춘 값이다.
    Thor 에서 연구개발 사람영상 330편(쓰러짐)을 40시간 돌려 트랙별 창 점수를 받아 두었다(tools/fall_dump_all.py).
    규칙은 파일만 읽어 즉시 훑을 수 있다. 판정·채점 함수는 scripts/fall_sweep.py 것을 그대로 쓴다.

주의 (2026-09-20 오전 확인)
    dumps/fall_seq_dev330 의 330편은 배포 SeqNet 의 학습 영상이다(feats/fall_kpts 와 330/330 겹침). 거기서 나온 점수는
    학습셋 점수다. 학습에 안 쓴 곡선은 scripts/fall_cv330.py(장면 묶음 교차검증) 와 scripts/fall_dump_aihub.py(AI허브 35편)가 만든다.

무엇을 보나
    지금 값(0.755·4)과 후보(0.80·5)의 점수 · 최고 조합 · 고원(같은 점수 조합 수) · LOOCV(한 편 빼고 고른 절차의 점수)
    · 조건별(주간/야간) 점수 · 지금 값에서 틀리는 편

사용
    python scripts/fall_sweep330.py [덤프폴더] [시작무시초]
    시작무시초: 영상 시작 뒤 그 초까지의 창은 버린다(이른 오검 억제 후보). 기본 0.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
import fall_sweep as F      # noqa: E402  (fire_time · score · SLOT · WIN 을 그대로 쓴다)
import rule_common as RC    # noqa: E402
import kisa_items as K      # noqa: E402
import kisa_paths as KP     # noqa: E402

CUR = (K.ITEMS["falldown"]["th"], K.ITEMS["falldown"]["need"])   # 지금 배포 값(제출 도구에서 읽는다. 2026-09-20 부터 0.80·5)
DELAY = float(K.ITEMS["falldown"].get("delay", 0.0))              # 배포 경보 지연(2026-09-20 부터 1초). 곡선 시각에 더해 적용
CAND = (0.755, 4)           # 비교용: 2026-09-20 이전 값
RAW = V / "data/원본데이터/kisa_연구개발_사람영상"
GRID = [(th, need) for th in (0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.755, 0.80, 0.85, 0.90, 0.95)
        for need in (2, 3, 4, 5, 6, 7, 8, 10)]


def tod_of(stem):
    for x in RAW.rglob(stem + ".xml"):
        try:
            return ET.parse(x).getroot().findtext(".//Weather/TimeOfDay") or "?"
        except Exception:
            return "?"
    return "?"


def main():
    dd = Path(sys.argv[1] if len(sys.argv) > 1 else "dumps/fall_seq_dev330")
    warm = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    clips, tods = [], {}
    for f in sorted(dd.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("gt") is None:                                   # 채점 견본 덤프(dump_clip)는 정답이 없다 → XML 에서
            mp4 = next(KP.videos("쓰러짐").rglob(f.stem + ".mp4"), None)
            d["gt"] = F.gt_of(mp4) if mp4 else None
        if d.get("gt") is None:
            continue
        curves = [[[p[0] + DELAY, p[1]] for p in cur if p[0] >= warm] for cur in (d.get("curves") or [])]
        clips.append((f.stem, float(d["gt"]), curves))
        tods[f.stem] = d.get("tod") or tod_of(f.stem)      # 덤프에 조건이 있으면 그것, 없으면 KISA XML
    print("쓰러짐 %d편 · 덤프 %s · 조합 %d · 시작 %.0f초 무시 · 경보 지연 %.1f초(ITEMS)" % (len(clips), dd, len(GRID), warm, DELAY))
    empty = sum(1 for _s, _g, c in clips if not any(c))
    print("  트랙(곡선)이 하나도 없는 편 %d" % empty)

    res = []
    for th, need in GRID:
        f1, tp, fn, fp, det = F.score(clips, th, need)
        res.append((f1, th, need, tp, fn, fp, {s: sa for s, _v, sa in det}))
    cur = next(r for r in res if (r[1], r[2]) == CUR)
    cand = next(r for r in res if (r[1], r[2]) == CAND)
    res_sorted = sorted(res, key=lambda r: (-r[0], -r[1], r[2]))
    top = res_sorted[0][0]
    flat = sum(1 for r in res if r[0] >= top - 0.01)
    print("\n  지금 값 th %.3f need %d : %6.2f (정검 %d · 미검 %d · 오검 %d)" % (CUR[0], CUR[1], cur[0], cur[3], cur[4], cur[5]))
    print("  이전값 th %.3f need %d : %6.2f (정검 %d · 미검 %d · 오검 %d)" % (CAND[0], CAND[1], cand[0], cand[3], cand[4], cand[5]))
    print("  최고               : %6.2f  th %.3f need %d (정검 %d · 미검 %d · 오검 %d)  고원 %d%s"
          % (top, res_sorted[0][1], res_sorted[0][2], res_sorted[0][3], res_sorted[0][4], res_sorted[0][5], flat, "" if flat >= 5 else "  <- 봉우리"))
    gt = {s: g for s, g, _c in clips}
    lo = RC.loocv([((r[1], r[2]), r[6]) for r in res], gt, "F", CUR)
    print("  " + RC.fmt_loocv(lo))
    print("\n  th × need 표 (%d편 F1):" % len(clips))
    needs = sorted(set(n for _t, n in GRID))
    print("    th    " + "".join("  need%-2d" % n for n in needs))
    for th in sorted(set(t for t, _n in GRID)):
        line = "    %.3f " % th
        for n in needs:
            r = next(r for r in res if (r[1], r[2]) == (th, n))
            line += "  %6.2f" % r[0]
        print(line + ("   <- 지금" if abs(th - CUR[0]) < 1e-9 else "") + ("   <- 후보 행" if abs(th - CAND[0]) < 1e-9 else ""))
    # 조건별(주간/야간) : 지금 값 · 후보 · 최고 값
    for label, (th, need) in (("지금 값", CUR), ("후보", CAND), ("최고", (res_sorted[0][1], res_sorted[0][2]))):
        line = "  %-5s 조건별:" % label
        for tod in sorted(set(tods.values())):
            sub = [c for c in clips if tods[c[0]] == tod]
            f1, tp, fn, fp, _ = F.score(sub, th, need)
            line += "  %s %6.2f (%d편, 정검 %d 미검 %d 오검 %d)" % (tod, f1, len(sub), tp, fn, fp)
        print(line)
    # 지금 값·후보에서 틀리는 편 목록(원인 가르기용)
    for label, rule in (("지금 값", CUR), ("후보", CAND)):
        _f1, _tp, _fn, _fp, det = F.score(clips, *rule)
        bad = [(s, v, sa) for s, v, sa in det if v != "정검"]
        print("\n  %s에서 틀리는 편 %d: " % (label, len(bad)) + ", ".join("%s(%s%s)" % (s, v, ("" if sa is None else " %.1f/정답 %.0f" % (sa, gt[s]))) for s, v, sa in bad[:40]))


if __name__ == "__main__":
    main()

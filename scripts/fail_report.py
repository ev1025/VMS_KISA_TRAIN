# -*- coding: utf-8 -*-
"""못 잡은 편·잘못 잡은 편의 원인을 편마다 가르고, 촬영 조건별로 모아 '어떤 데이터가 더 필요한가' 를 낸다.

왜 (2026-09-18)
    "미검·오검 이유와 내가 가져와야 할 데이터를 알려달라" 는 요청.
    점수만 보면 무엇을 채워야 할지 알 수 없다. 편마다 어디서 끊겼는지를 봐야 한다.

원인 가르기 (침입·배회 공통, 덤프만 보고 판정 단계를 되짚는다)
    검출없음    구역 안에서 어떤 신뢰도로도 사람 박스가 안 나왔다              -> 모델이 못 본다
    약한검출    구역 안에 박스는 있는데 최대 신뢰도가 문턱 미만               -> 조금 더 밝게/크게 보이면 넘는다
    체류부족    문턱은 넘는데 요구 길이(침입 hold · 배회 체류)를 못 채운다      -> 트랙이 끊긴다(가림·교차·저해상)
    조기경보    정답보다 훨씬 이른 시각에 조건을 채워 확정됐다                 -> 시작부터 있던 물체·구역 경계
    지연        조건은 채웠는데 시각이 창보다 늦다                          -> 검출이 늦게 붙는다
    구역밖      정답 시각 근처에 박스는 있는데 구역 판정(발끝·꼭짓점)에서 잘린다

조건 (정답 xml 의 Header/Weather 를 그대로 읽는다)
    TimeOfDay · Rain · Snow · Fog · Location · Distraction

사용
    python scripts/fail_report.py intrusion [라벨=덤프 ...]
    python scripts/fail_report.py loiter    [라벨=덤프 ...]
"""
import collections
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K      # noqa: E402
import kisa_paths as KP     # noqa: E402
import intr_rule4 as I      # noqa: E402
import loiter_rule4 as L    # noqa: E402

DEFAULT = {
    "intrusion": ["배포=dumps/intrusion_tile_v3", "손32.6=dumps/intrusion_p1280hand_1280",
                  "손10.8=dumps/intrusion_p1280ov2_1280"],
    "loiter": ["배포=dumps/loiter_botsort_v2", "손32.6=dumps/loiter_p1280hand_bs1280",
               "손10.8=dumps/loiter_p1280ov2_bs1280"],
}
ITEM_KR = {"intrusion": "침입", "loiter": "배회"}


def conds(item, stem):
    """정답 xml 에서 촬영 조건을 읽는다."""
    g = next(KP.videos(ITEM_KR[item]).rglob(stem + ".xml"), None)
    if g is None:
        return {}
    try:
        h = ET.parse(g).getroot().find(".//Clip/Header")
        w = h.find("Weather")
        return {"시간": (w.findtext("TimeOfDay") or "?"), "비": (w.findtext("Rain") or "?"),
                "눈": (w.findtext("Snow") or "?"), "안개": (w.findtext("Fog") or "?"),
                "장소": (h.findtext("Location") or "?"), "방해물": (h.findtext("Distraction") or "?")}
    except Exception:
        return {}


def diagnose(item, rows, poly, gt, sa):
    """판정 단계를 되짚어 원인 하나와 근거 숫자를 돌려준다."""
    CFG = (I if item == "intrusion" else L).CFG
    th, corners = CFG["conf"], CFG["corners"]
    near = [r for r in rows if gt - 20 <= r["t"] <= gt + 20]          # 사건 앞뒤 20초
    inz = [(r["t"], b) for r in near for b in r["boxes"] if K.entered((b[2], b[3], b[4], b[5]), poly, corners)]
    anyz = [(r["t"], b) for r in near for b in r["boxes"]]
    mx = max([b[1] for _t, b in inz], default=0.0)
    hi = [(t, b) for t, b in inz if b[1] >= th]
    # 트랙별 최장 연속 체류(끊김 gap 표본 허용)
    step = CFG.get("stride", 0.5)
    run = collections.defaultdict(float); last = {}
    for t, b in hi:
        pid = b[0]
        run[pid] = step if pid not in last or t - last[pid] > step * (CFG.get("gap", 2) + 1) else run[pid] + step
        last[pid] = t
    dwell = max(run.values(), default=0.0)
    need = CFG.get("dwell", CFG.get("hold", 2) * step)
    first_hi = min((t for t, _b in hi), default=None)
    if sa is not None and sa < gt - 2:
        why, ev = "조기경보", "경보 %.1fs = 정답보다 %.1fs 이르다" % (sa, gt - sa)
    elif sa is not None and sa > gt + 10:
        why, ev = "지연", "경보 %.1fs = 정답보다 %.1fs 늦다" % (sa, sa - gt)
    elif not anyz:
        why, ev = "검출없음", "사건 앞뒤 20초에 박스 0개"
    elif not inz:
        why, ev = "구역밖", "박스 %d개 전부 구역 판정에서 잘림" % len(anyz)
    elif mx < th:
        why, ev = "약한검출", "구역 안 최대 신뢰도 %.2f < 문턱 %.2f" % (mx, th)
    elif dwell < need - 1e-6:
        why, ev = "체류부족", "최장 체류 %.1fs < 요구 %.1fs (구역 안 문턱이상 %d표본)" % (dwell, need, len(hi))
    else:
        why, ev = "그밖", "구역 안 문턱이상 %d표본 · 최장 체류 %.1fs · 첫 시각 %s" % (
            len(hi), dwell, ("%.1f" % first_hi) if first_hi else "-")
    return why, ev, mx, len(hi), dwell


def main():
    item = sys.argv[1] if len(sys.argv) > 1 else "intrusion"
    M = I if item == "intrusion" else L
    specs = sys.argv[2:] or DEFAULT[item]
    print("== %s · 미검·오검 원인 (덤프 %d벌, 지금 규칙 기준)\n" % (ITEM_KR[item], len(specs)))
    by_cause = collections.Counter()
    by_cond = collections.defaultdict(lambda: [0, 0])       # 조건값 -> [실패, 전체]
    hard = collections.Counter()                            # 모든 모델이 못 잡은 편
    for spec in specs:
        label, path = spec.split("=", 1)
        rows, poly, gt = M.load(path)
        if not rows:
            print("(덤프 없음) " + path); continue
        print("-- %s (%s)" % (label, path))
        for s in sorted(rows):
            g = gt[s]
            if g is None:
                continue
            sa = M.sa_entry(rows[s], poly[s], **M.NOW)
            ok = sa is not None and g - 2 <= sa <= g + 10
            c = conds(item, s)
            for k, v in c.items():
                by_cond[(k, v)][1] += 1
                if not ok:
                    by_cond[(k, v)][0] += 1
            if ok:
                continue
            why, ev, mx, nhi, dwell = diagnose(item, rows[s], poly[s], g, sa)
            by_cause[why] += 1
            hard[s] += 1
            print("   %-12s %-6s %-8s %s   [%s]" % (s.replace("C00_", ""), "미검" if sa is None else "오검", why, ev,
                                                  " ".join("%s=%s" % (k, v) for k, v in c.items() if v not in ("No", "None", "?"))))
        print()
    print("원인 집계: " + " · ".join("%s %d" % (k, v) for k, v in by_cause.most_common()))
    n = len(specs)
    allbad = sorted(s for s, c in hard.items() if c >= n)
    print("모든 모델이 못 잡은 편(%d): %s" % (len(allbad), ", ".join(x.replace("C00_", "") for x in allbad)))
    print("\n조건별 실패율(실패/전체, 3벌 합산):")
    for (k, v), (bad, tot) in sorted(by_cond.items(), key=lambda x: -(x[1][0] / max(1, x[1][1]))):
        if tot >= 3 and bad:
            print("   %-6s %-16s %2d/%2d = %3.0f%%" % (k, v, bad, tot, 100.0 * bad / tot))


if __name__ == "__main__":
    main()

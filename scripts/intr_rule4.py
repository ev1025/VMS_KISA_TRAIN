# -*- coding: utf-8 -*-
"""침입 규칙에 '들어온 사람만 인정'·'히스테리시스' 조건을 넣고 훑는다. 덤프만 쓴다.

무엇을 봤나 (2026-09-18, 손라벨 모델 덤프 편별 분해)
    손라벨 모델의 미검 8편 중 3편(170·239·275)은 경보가 1.0초·2.5초·33.5초에 났다.
    영상 시작부터 구역 안에 무언가 있고 손라벨 모델이 그걸 사람으로 본다(239편은 첫 30초의
    60표본 중 29표본이 conf 0.45 이상). settle 24초 뒤 확정돼 진짜 침입(115~134초)은 아예 안 잡힌다.
    배포 모델은 그 물체를 0.22 이하로 봐서 이 문제가 없었다. 검출이 좋아져 생긴 문제다.
    나머지 미검(255·249·014·126)은 구역 안에서 0.47~0.67 로 잡히는데 corners=3 · hold=2 에서 잘린다.

조건 셋 (앞의 둘은 '침입 = 들어오는 사건' 이라는 정의에서, 셋째는 '깜빡이는 검출 이어붙이기' 에서 나온다)
    warm_s    영상 시작 warm_s 초 안에 구역 안에서 처음 보인 트랙은 원래 있던 것으로 보고 무시한다.
    out_need  트랙이 구역 안에 들어오기 전에 구역 밖에서 out_need 표본 이상 보였어야 한다. 0 이면 끔.
    lo·win_s  히스테리시스. conf_th(높은 문턱)를 한 번 넘긴 트랙은 win_s 초 동안 lo(낮은 문턱)까지 인정한다.
              0 이면 끔. intr_rule3 의 hyst 가 ov2 모델에서 94.74 를 냈는데, 그 스크립트는 경보 시각을
              자기 식으로 찍어서(streak 시작 시각) 실제 규칙과 다르다. 여기서 실제 판정기로 다시 잰다.

구현 원칙
    판정기는 제출 도구의 IntrusionRule 을 그대로 쓴다(복사·재구현 금지). 박스만 걸러서 넣는다.
    IntrusionRule 은 conf 를 'conf < 문턱이면 버림' 으로만 쓴다. 그래서 히스테리시스는
    판정기 문턱을 lo 로 내리고, 켜지지 않은 트랙의 lo~conf_th 박스를 여기서 미리 빼면 된다.
    그래서 warm 0 · out 0 · lo 0 은 반드시 지금 규칙과 같은 값이 나온다. 시작할 때 그걸 검사한다(--selfcheck 자동).
    (처음 판은 규칙을 다시 구현했다가 기준선이 94.74 가 아니라 84.21 로 나와 버렸다. 2026-09-18)

사용
    python scripts/intr_rule4.py [덤프폴더 ...]
"""
import itertools
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402
import rule_common as RC  # noqa: E402
from loiter_rule4 import dedupe_boxes  # noqa: E402  중복 박스 정리(배회와 같은 구현)

CFG = K.ITEMS["intrusion"]
NOW = dict(conf_th=CFG["conf"], corners=CFG["corners"], hold=CFG["hold"], gap=CFG["gap"],
           warm_s=0, out_need=0, lo=0, win_s=3.0, dedupe=0, settle=CFG["settle"])
OUT_CONF = 0.15                     # 구역 밖에서 '보였다' 로 칠 최소 신뢰도(덤프 바닥값)
EPS = getattr(K, "T_EPS", 1e-6)


def load(dump):
    d = Path(dump)
    rows, poly, gt = {}, {}, {}
    for f in sorted(d.glob("*.jsonl")):
        s = f.stem
        rows[s] = [json.loads(l) for l in f.read_text().splitlines()]
        poly[s] = K.zone_of(str(KP.ZONE_MAPS), s, CFG["zone"], (1280, 720))
        g = next(KP.videos("침입").rglob(s + ".xml"), None)
        a = K.read_alarms(g) if g else []
        gt[s] = a[0]["start_s"] if a else None
    return rows, poly, gt


def sa_entry(rows, poly, conf_th, corners, hold, gap, warm_s, out_need, lo=0, win_s=3.0, dedupe=0, settle=CFG["settle"]):
    """제출 도구의 판정기에, 무시할 트랙·켜지지 않은 트랙의 박스만 빼고 넣는다. settle = 마지막 진입 뒤 확정까지 기다리는 초(배포 24)."""
    j = K.IntrusionRule(poly, lo if lo else conf_th, corners, hold, settle, gap)
    outside, first_in, ignore, last_hi = {}, {}, set(), {}
    for r in rows:
        t = r["t"]
        keep = []
        for b in (dedupe_boxes(r["boxes"], dedupe) if dedupe else r["boxes"]):
            pid, conf, x1, y1, x2, y2 = b
            if lo:
                if conf >= conf_th:
                    last_hi[pid] = t                                # 높은 문턱을 넘긴 마지막 시각
                elif not (pid in last_hi and t - last_hi[pid] <= win_s + EPS):
                    continue                                        # 켜진 적 없는(또는 식은) 트랙의 낮은 박스는 버린다
            inside = K.entered((x1, y1, x2, y2), poly, corners)
            if not inside:
                if conf >= OUT_CONF and pid not in first_in:
                    outside[pid] = outside.get(pid, 0) + 1     # 들어오기 전에 밖에서 본 횟수
            elif pid not in first_in:
                first_in[pid] = t
                if t < warm_s:                                  # 시작부터 안에 있던 것
                    ignore.add(pid)
                elif out_need and outside.get(pid, 0) < out_need:   # 밖에서 본 적 없이 안에 나타남
                    ignore.add(pid)
            if pid not in ignore:
                keep.append(b)
        j.feed(t, keep)
    return j.final()


def sa_now(rows, poly):
    j = K.IntrusionRule(poly, CFG["conf"], CFG["corners"], CFG["hold"], CFG["settle"], CFG["gap"])
    for r in rows:
        j.feed(r["t"], r["boxes"])
    return j.final()


def zone_max_conf(rows, poly):
    return max([b[1] for r in rows for b in r["boxes"] if K.entered((b[2], b[3], b[4], b[5]), poly, 3)] or [0.0])


def run(rows, poly, gt, zmax, fn):
    pairs, miss, offs, edge, tp_c, fn_c, sas = [], [], [], [], [], [], {}
    for s in rows:
        sa = fn(s); sas[s] = sa
        pairs.append(([{"start_s": gt[s], "desc": "I"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "I"}] if sa is not None else []))
        if gt[s] is None:
            continue
        ok = sa is not None and gt[s] - 2 <= sa <= gt[s] + 10
        if ok:
            offs.append(sa - gt[s]); edge.append(min(sa - (gt[s] - 2), (gt[s] + 10) - sa)); tp_c.append(zmax[s])
        else:
            miss.append(s.replace("C00_", "")); fn_c.append(zmax[s])
    r = K.score(pairs)
    return dict(score=r["점수"], tp=r["정상검출"], fn=r["미검출"], fp=r["오검출"], miss=miss, sa=sas,
                off=(sum(offs) / len(offs)) if offs else 0, edge=min(edge) if edge else 0,
                gap=(min(tp_c) - max(fn_c)) if tp_c and fn_c else None)


def fmt(r):
    return "%6.2f (%2d/%d/%d) 창위치 +%.1fs 여유 %.1fs 간격 %s" % (
        r["score"], r["tp"], r["fn"], r["fp"], r["off"], r["edge"], ("%.2f" % r["gap"]) if r["gap"] is not None else "-")


GRID = dict(conf_th=[0.35, 0.40, 0.45], corners=[0, 2, 3], hold=[1, 2], gap=[2],
            warm_s=[0, 5, 10, 20], out_need=[0, 1, 2], lo=[0, 0.15, 0.20], win_s=[3.0], dedupe=[0, 0.5], settle=[CFG["settle"]])
# settle · hold 3~4 · gap 3~6 같은 넓은 축은 scripts/intr_wide.py 가 따로 훑는다(여기 격자에 다 넣으면 조합이 만 단위로 커진다).

def main(dumps=None):
    dumps = dumps or sys.argv[1:] or ["dumps/intrusion_tile_v3", "dumps/intrusion_p1280hand_1280", "dumps/intrusion_p1280ov2_1280"]
    for dump in dumps:
        rows, poly, gt = load(dump)
        if not rows:
            print("\n===== %s : 덤프 없음" % dump); continue
        zmax = {s: zone_max_conf(rows[s], poly[s]) for s in rows}

        # 자기검사: 필터를 끈 감싸기(warm 0 · out 0 · lo 0)가 제출 도구 판정과 편마다 똑같은 경보 시각을 내야 한다
        bad = [s for s in rows if sa_now(rows[s], poly[s]) != sa_entry(rows[s], poly[s], **NOW)]
        if bad:
            print("\n===== %s : 자기검사 실패. 감싸기가 실제 규칙과 다르다: %s" % (dump, bad)); continue

        keys = list(GRID)
        res = [(run(rows, poly, gt, zmax, lambda s, kw=dict(zip(keys, v)): sa_entry(rows[s], poly[s], **kw)), dict(zip(keys, v)))
               for v in itertools.product(*GRID.values())]
        now = next(r for r, kw in res if kw == NOW)
        res.sort(key=lambda x: (-x[0]["score"], -x[0]["edge"], -(x[0]["gap"] if x[0]["gap"] is not None else -9)))
        top = res[0][0]["score"]
        flat = sum(1 for r, _ in res if r["score"] >= top - 0.01)
        print("\n===== %s   %d편   (%d조합 · 자기검사 통과)" % (dump, len(rows), len(res)))
        print("  지금 규칙   %s" % fmt(now))
        print("              못잡음 %s" % now["miss"])
        print("  최고        %s  고원 %d%s" % (fmt(res[0][0]), flat, "" if flat >= 5 else "  <- 봉우리"))
        print("              못잡음 %s" % res[0][0]["miss"])
        print("              설정   %s" % res[0][1])
        lo = RC.loocv([(kw, r["sa"]) for r, kw in res], {s: g for s, g in gt.items() if g is not None}, "I", NOW)
        print("  %s" % RC.fmt_loocv(lo))
        print("  (conf·corners·hold·gap 은 지금 값 고정) warm_s × out_need:")
        for w in GRID["warm_s"]:
            line = "    warm %2ds :" % w
            for o in GRID["out_need"]:
                r = next(r for r, kw in res if kw == dict(NOW, warm_s=w, out_need=o))
                line += "  out%d %6.2f(%2d/%d/%d)" % (o, r["score"], r["tp"], r["fn"], r["fp"])
            print(line)
        print("  중복 박스 정리(dedupe 0.5, 다른 값은 지금 값) : %s" % fmt(next(r for r, kw in res if kw == dict(NOW, dedupe=0.5))))
        rb, kb = next((r, kw) for r, kw in res if kw["dedupe"] == 0.5)
        print("              dedupe 0.5 중 최고 %s  설정 conf %.2f corners %d hold %d warm %d lo %.2f" % (fmt(rb), kb["conf_th"], kb["corners"], kb["hold"], kb["warm_s"], kb["lo"]))
        print("  히스테리시스(lo) : 다른 값은 지금 값 고정 / 그 lo 에서 제일 나은 조합")
        for lo in GRID["lo"]:
            r0 = next(r for r, kw in res if kw == dict(NOW, lo=lo))
            rb, kb = next((r, kw) for r, kw in res if kw["lo"] == lo)      # res 는 점수순 정렬돼 있다
            nb = sum(1 for r, kw in res if kw["lo"] == lo and r["score"] >= rb["score"] - 0.01)
            print("    lo %.2f : 지금값 %6.2f(%2d/%d/%d)   최고 %s  고원 %d  설정 conf %.2f corners %d hold %d warm %d out %d"
                  % (lo, r0["score"], r0["tp"], r0["fn"], r0["fp"], fmt(rb), nb,
                     kb["conf_th"], kb["corners"], kb["hold"], kb["warm_s"], kb["out_need"]))
            print("              못잡음 %s" % rb["miss"])


if __name__ == "__main__":
    main()

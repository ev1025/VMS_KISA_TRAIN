# -*- coding: utf-8 -*-
"""배회 규칙에 '시작부터 구역 안에 있던 트랙 무시(warm_s)' 를 넣고 훑는다. 덤프만 쓴다.

왜 (2026-09-18)
    손라벨 모델 두 편은 배회에서 지금 규칙으로 82.76(오검 4) 이고, 1,800조합을 훑어도 86~88 이다(배포 96.55).
    침입에서 같은 모델들의 오검 원인이 '영상 시작부터 구역 안에 있던 물체를 사람으로 봄' 이었다(intr_rule4).
    배회는 구역 안 체류 6초면 경보라 그 물체가 바로 오검이 된다. 같은 처방이 통하는지 본다.
    오검 편은 어디서 경보가 났는지(경보 시각 · 정답 시각)도 같이 찍어 원인이 그것인지 눈으로 확인한다.

프레임으로 확인한 진짜 원인 (2026-09-18, dump_frame_boxes · loiter_fp_timeline)
    warm_s 는 효과가 없었다(오검 4편 모두 영상 중간). 원인은 두 가지.
    (a) 손라벨 모델은 한 사람에 박스를 2~3개 낸다(우산 포함 박스 + 몸 박스, 전신 + 상반신). 트랙도 2~3개가 된다.
        LoiterRule 은 '늦게 온 일행' 을 받을 때 구역 인원 <= crowd(3) 를 요구하는데, 중복 박스가 인원을 부풀려
        뒤에 들어온 진짜 마지막 사람을 거절한다 -> 첫 사람 기준으로 확정 -> 경보가 8~15초 이르다(211·232·260).
        013 은 반대로 같은 사람의 두 번째 박스가 '방금 도착한 새 사람' 으로 받아들여져 경보가 18초 늦다.
    (b) 야간 IR 에서 배포 모델은 사람을 4~12초 늦게 잡는다(232: 104.5초에 두 명이 구역 안에 있는데 108.5초까지 0박스).
        정답 시각과 규칙(+10초) 이 배포 모델의 늦은 검출에 맞춰져 있었다. 이건 규칙이 아니라 정답 관례 문제라 여기서 못 고친다.
    그래서 (a) 를 겨냥해 두 조건을 더 본다.
    dedupe    한 표본 안에서 겹치는 박스(교집합 / 작은 박스 넓이 >= dedupe)는 conf 낮은 쪽을 버린다. 0 이면 끔.
    crowd     '늦게 온 일행' 을 받아 주는 구역 인원 상한(배포 3).
    (b) 는 규칙으로 못 고친다고 적었다가 틀렸음을 지적받았다(2026-09-18). 경보 시각 = 마지막 사람 진입 + delay 인데
        delay(배포 10초)는 배포 모델의 검출 시점에 맞춰 정한 상수다. 먼저 보는 모델이면 delay 를 늘리면 된다.
    delay     진입 시각에 더하는 초. 배포 10. 모델마다 검출이 빠르고 늦은 만큼 다르게 맞출 수 있다.

구현 원칙
    판정기는 제출 도구의 LoiterRule 을 그대로 쓴다(복사·재구현 금지). 박스만 걸러 넣고 crowd 만 인자로 바꾼다.
    warm 0 · dedupe 0 · crowd 3 은 지금 규칙과 편마다 같은 경보 시각을 내야 한다(자기검사 자동).

사용
    python scripts/loiter_rule4.py [덤프폴더 ...]
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

CFG = K.ITEMS["loitering"]
STEP = CFG["stride"]
DELAY = CFG["delay"]
NOW = dict(conf_th=CFG["conf"], dwell=CFG["dwell"], warm_s=0, dedupe=0, crowd=CFG["crowd"], delay=DELAY,
           alias=0, gap=CFG["gap"], settle=CFG["settle"], margin=CFG.get("margin", 0))   # 2026-09-20: 지금 규칙 = ITEMS(margin 10)


def foot_inside(box, poly, margin):
    """발끝(하단 중앙)이 구역 안에 margin 픽셀 여유를 두고 들어와 있나. 좌우로 margin 만큼 옮겨도 안이어야 한다.
    (232편: 구역 경계를 따라 걷는 사람을 발끝 몇 픽셀 차로 '안' 으로 보아 오검. 2026-09-18)"""
    x1, _y1, x2, y2 = box
    cx = (x1 + x2) / 2
    return K.in_poly(cx - margin, y2, poly) and K.in_poly(cx + margin, y2, poly)


def load(dump):
    d = Path(dump)
    rows, poly, gt = {}, {}, {}
    for f in sorted(d.glob("*.jsonl")):
        s = f.stem
        rows[s] = [json.loads(l) for l in f.read_text().splitlines()]
        poly[s] = K.zone_of(str(KP.ZONE_MAPS), s, CFG["zone"], (1280, 720))
        g = next(KP.videos("배회").rglob(s + ".xml"), None)
        a = K.read_alarms(g) if g else []
        gt[s] = a[0]["start_s"] if a else None
    return rows, poly, gt


def make_rule(poly, conf_th, dwell, crowd=CFG["crowd"], gap=CFG["gap"], settle=CFG["settle"], margin=0):
    """margin 은 sa_entry 가 상자를 미리 걸러 넣으므로 기본 0. sa_now(지금 규칙)만 ITEMS 의 margin 을 규칙 안에서 쓴다(2026-09-20)."""
    return K.LoiterRule(poly, conf_th, CFG["corners"], dwell, settle, gap, STEP,
                        CFG["maxgap"], crowd, CFG["still_in"], margin=margin)


def dedupe_boxes(boxes, thr, alias=None):
    """겹치는 박스 정리: 교집합이 작은 쪽 넓이의 thr 이상이면 conf 낮은 박스를 버린다(같은 사람에 난 중복 박스).
    alias 딕셔너리를 주면 버린 박스의 트랙 번호를 남긴 박스의 번호로 기억해 두고, 다음 표본부터 그 번호를 바꿔 넣는다.
    (2026-09-18 추적 결과: 같은 사람의 두 트랙이 표본마다 번갈아 살아남아 '고른 사람이 아직 안에 있나' 검사가 깨졌다.)"""
    if alias is not None:
        boxes = [(alias.get(b[0], b[0]),) + tuple(b[1:]) for b in boxes]
    keep = []
    for b in sorted(boxes, key=lambda b: -b[1]):
        pid, _c, x1, y1, x2, y2 = b
        area = max(1e-6, (x2 - x1) * (y2 - y1))
        dup = None
        for k in keep:
            ix = max(0.0, min(x2, k[4]) - max(x1, k[2])); iy = max(0.0, min(y2, k[5]) - max(y1, k[3]))
            karea = max(1e-6, (k[4] - k[2]) * (k[5] - k[3]))
            if ix * iy / min(area, karea) >= thr:
                dup = k; break
        if dup is None:
            keep.append(b)
        elif alias is not None and pid != dup[0]:
            alias[pid] = dup[0]                       # 이 트랙은 앞으로 남긴 트랙의 번호로 부른다
    return keep


def finish(j, sa, delay=DELAY):
    """feed 가 낸 첫 값이 없으면 final() 로 마무리. 경보 시각 = 체류 시작 + delay (배포는 10초)."""
    if sa is None:
        v = j.final() if hasattr(j, "final") else None
        sa = (v + delay) if v is not None else None
    return sa


def sa_now(rows, poly):
    j = make_rule(poly, CFG["conf"], CFG["dwell"], margin=CFG.get("margin", 0))   # 지금 규칙 = 제출 도구 상수 그대로
    sa = None
    for r in rows:
        v = j.feed(r["t"], r["boxes"])
        if v is not None and sa is None:
            sa = v + DELAY
    return finish(j, sa)


def sa_entry(rows, poly, conf_th, dwell, warm_s, dedupe=0, crowd=CFG["crowd"], delay=DELAY,
             alias=0, gap=CFG["gap"], settle=CFG["settle"], margin=0):
    """제출 도구의 판정기에, 시작 warm_s 초 안에 구역 안에서 처음 보인 트랙·중복 박스만 빼고 넣는다. 경보 = 진입 + delay.
    alias=1 이면 중복으로 버린 트랙 번호를 남긴 트랙 번호로 합친다(한 사람 = 한 번호).
    margin>0 이면 발끝이 구역 경계에서 margin 픽셀 안쪽에 있어야 '안' 으로 친다(경계 걷는 사람 제외)."""
    j = make_rule(poly, conf_th, dwell, crowd, gap, settle)
    first_in, ignore, sa = {}, set(), None
    al = {} if (dedupe and alias) else None
    for r in rows:
        t = r["t"]
        keep = []
        for b in (dedupe_boxes(r["boxes"], dedupe, al) if dedupe else r["boxes"]):
            pid, conf, x1, y1, x2, y2 = b
            if margin and K.entered((x1, y1, x2, y2), poly, CFG["corners"]) and not foot_inside((x1, y1, x2, y2), poly, margin):
                continue                                        # 경계에 걸친 발끝은 구역 밖으로 친다
            if pid not in first_in and K.entered((x1, y1, x2, y2), poly, CFG["corners"]):
                first_in[pid] = t
                if t < warm_s:
                    ignore.add(pid)                         # 시작부터 안에 있던 것
            if pid not in ignore:
                keep.append(b)
        v = j.feed(t, keep)
        if v is not None and sa is None:
            sa = v + delay
    return finish(j, sa, delay)


def run(rows, poly, gt, fn):
    pairs, miss, fps, offs, edge, sas = [], [], [], [], [], {}
    for s in rows:
        sa = fn(s); sas[s] = sa
        pairs.append(([{"start_s": gt[s], "desc": "L"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "L"}] if sa is not None else []))
        ok = gt[s] is not None and sa is not None and gt[s] - 2 <= sa <= gt[s] + 10
        if ok:
            offs.append(sa - gt[s]); edge.append(min(sa - (gt[s] - 2), (gt[s] + 10) - sa))
        else:
            if gt[s] is not None:
                miss.append(s.replace("C00_", ""))
            if sa is not None:
                fps.append("%s(경보 %.1fs, 정답 %s)" % (s.replace("C00_", ""), sa, ("%.1fs" % gt[s]) if gt[s] is not None else "없음"))
    r = K.score(pairs)
    return dict(score=r["점수"], tp=r["정상검출"], fn=r["미검출"], fp=r["오검출"], miss=miss, fps=fps, sa=sas,
                off=(sum(offs) / len(offs)) if offs else 0, edge=min(edge) if edge else 0)


def fmt(r):
    return "%6.2f (%2d/%d/%d) 창위치 +%.1fs 여유 %.1fs" % (r["score"], r["tp"], r["fn"], r["fp"], r["off"], r["edge"])


# delay 10~16 은 이미 훑었다(2026-09-18): 배포는 10 이 아니면 바로 깨지고(여유 0.0), 손라벨은 89.66 평평 → 축에서 뺀다.
GRID = dict(conf_th=[0.35, 0.40], dwell=[4.0, 6.0], warm_s=[0], dedupe=[0], crowd=[3, 5], delay=[10.0, 12.0],
            alias=[0], gap=[6, 10], settle=[5.0, 8.0], margin=[0, 10, 20, 40])
# dedupe 0.5 는 채점 경로(BoT-SORT) 덤프에서는 겹친 박스가 0.2% 라 뺐다(타일 덤프에서만 뜻이 있었다). delay 14 는 배포·손라벨 모두 손해.


def main(dumps=None):
    dumps = dumps or sys.argv[1:] or ["dumps/loiter_botsort_v2", "dumps/loiter_p1280hand_1280", "dumps/loiter_p1280ov2_1280"]
    for dump in dumps:
        rows, poly, gt = load(dump)
        if not rows:
            print("\n===== %s : 덤프 없음" % dump); continue
        bad = [s for s in rows if sa_now(rows[s], poly[s]) != sa_entry(rows[s], poly[s], **NOW)]
        if bad:
            print("\n===== %s : 자기검사 실패. 감싸기가 실제 규칙과 다르다: %s" % (dump, bad)); continue
        keys = list(GRID)
        res = [(run(rows, poly, gt, lambda s, kw=dict(zip(keys, v)): sa_entry(rows[s], poly[s], **kw)), dict(zip(keys, v)))
               for v in itertools.product(*GRID.values())]
        now = next(r for r, kw in res if kw == NOW)
        res.sort(key=lambda x: (-x[0]["score"], -x[0]["edge"]))
        top = res[0][0]["score"]
        flat = sum(1 for r, _ in res if r["score"] >= top - 0.01)
        print("\n===== %s   %d편   (%d조합 · 자기검사 통과)" % (dump, len(rows), len(res)))
        print("  지금 규칙   %s" % fmt(now))
        print("              못잡음 %s" % now["miss"])
        print("              오검   %s" % now["fps"])
        print("  최고        %s  고원 %d%s" % (fmt(res[0][0]), flat, "" if flat >= 5 else "  <- 봉우리"))
        print("              못잡음 %s" % res[0][0]["miss"])
        print("              오검   %s" % res[0][0]["fps"])
        print("              설정   %s" % res[0][1])
        lo = RC.loocv([(kw, r["sa"]) for r, kw in res], {s: g for s, g in gt.items() if g is not None}, "L", NOW)
        print("  %s" % RC.fmt_loocv(lo))
        print("  (conf 0.40 · crowd 3 · delay 10 고정) 중복정리·번호합치기 × 체류/끊김/대기:  점수(맞음/놓침/오검)")
        for mg in GRID["margin"]:
            line = "    발끝여유 %2dpx :" % mg
            for dw in GRID["dwell"]:
                for gp in GRID["gap"]:
                    for st in GRID["settle"]:
                        r = next(r for r, kw in res if kw == dict(NOW, margin=mg, dwell=dw, gap=gp, settle=st))
                        line += "  체류%.0f끊김%d대기%.0f %6.2f(%2d/%d/%d)" % (dw, gp, st, r["score"], r["tp"], r["fn"], r["fp"])
            print(line)


if __name__ == "__main__":
    main()

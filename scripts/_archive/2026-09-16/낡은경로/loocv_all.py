# -*- coding: utf-8 -*-
# [주의] 경로가 낡았다(SP = scripts/ 기준인데 덤프는 dumps/ 에 있다). 그대로는 안 돈다.
#        판정도 kisa_items.py 와 별개 구현이라 값이 어긋난다. 고쳐 쓰기 전에는 결과를 믿지 말 것.
"""4항목을 비디오 단위 LOOCV 로 다시 채점한다.

왜 다시 재는가:
  지금까지 보고한 점수는 배포 영상 전부를 보고 규칙 값(임계·창·대기시간)을 고른 뒤
  그 영상들로 채점한 값이다. 규칙이 그 영상들에 맞춰진 상태라 점수가 부풀려진다.
  인증 본시험은 우리가 못 본 영상이고 규칙 값은 시험 전에 고정해 제출하므로,
  한 편을 가리고 나머지로 고른 규칙이 그 한 편에서도 통하는지가 실제 기대치에 가깝다.

방식: 영상 하나를 뺀 나머지로 최고 조합을 고르고 그 조합을 뺀 영상에 적용.
      전 영상 반복해 정검·미검·오검을 합산한다. 창 밖 알람은 오검과 미검을 동시에 받는다.
"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import numpy as np

SP = Path(__file__).parent
BEFORE, AFTER = 2.0, 10.0


def f1_of(tp, fn, fp):
    recall = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    if recall + precision == 0:
        return 0.0
    return round(2 * recall * precision / (recall + precision) * 100, 2)


def verdict(alarm, answer):
    if alarm is None:
        return "미검"
    return "정검" if answer - BEFORE <= alarm <= answer + AFTER else "오검"


def tally(verdicts):
    tp = sum(v == "정검" for v in verdicts)
    fp = sum(v == "오검" for v in verdicts)
    fn = sum(v == "미검" for v in verdicts) + fp
    return tp, fn, fp


def loocv(names, alarm_fn, combos, answers):
    """alarm_fn(name, combo) 는 알람 시각 또는 None 을 돌려준다."""
    cache = {}
    for combo in combos:
        cache[combo] = {n: verdict(alarm_fn(n, combo), answers[n]) for n in names}

    full = {c: f1_of(*tally(list(v.values()))) for c, v in cache.items()}
    best_full = max(full, key=full.get)

    held_verdicts, picks = [], {}
    for held in names:
        rest = [n for n in names if n != held]
        scored = {c: f1_of(*tally([cache[c][n] for n in rest])) for c in combos}
        pick = max(scored, key=scored.get)
        picks[held] = pick
        held_verdicts.append(cache[pick][held])
    return full[best_full], best_full, f1_of(*tally(held_verdicts)), held_verdicts, picks


# ---------------- 방화 ----------------
def fire_setup(tag="human_full"):
    src = json.load(open(SP / f"{tag}.json", encoding="utf-8"))
    rows = {k: [tuple(r) for r in v["rows"]] for k, v in src.items()}
    answers = {k: float(v["gt"]) for k, v in src.items()}

    base = {}
    for k, rs in rows.items():
        head = sorted(s for t, _f, s in rs if t <= 60.0)
        base[k] = head[min(int(len(head) * 0.8), len(head) - 1)] if head else 0.0

    def alarm(name, combo):
        fth, win, hits, rise = combo
        q = []
        for t, fire, smoke in rows[name]:
            hit = fire >= fth
            if not hit and rise is not None:
                hit = smoke >= base[name] + rise and smoke >= 0.3
            q.append((t, hit))
            if len(q) > win:
                q.pop(0)
            if sum(1 for _t, h in q if h) >= hits:
                return next(t0 for t0, h in q if h) + 10.0
        return None

    combos = [(f, w, h, r)
              for f in (0.12, 0.18, 0.25, 0.30, 0.40, 0.50)
              for w, h in ((4, 3), (6, 4), (8, 4), (10, 5), (12, 7), (16, 7), (16, 9), (20, 9), (20, 12))
              for r in (None, 0.15, 0.20, 0.30)]
    return list(rows), alarm, combos, answers


# ---------------- 사람 항목 공통 ----------------
def load_person(dump_dir, gt_dir, zone_tags):
    dumps, answers, zones = {}, {}, {}
    for p in sorted((SP / dump_dir).glob("*.jsonl")):
        dumps[p.stem] = [json.loads(l) for l in p.read_text().splitlines()]
        alarm = ET.parse(SP / gt_dir / f"{p.stem}.xml").getroot().find(".//Alarm")
        h, m, s = alarm.findtext("StartTime").split(":")
        answers[p.stem] = int(h) * 3600 + int(m) * 60 + int(s)
        loc = "_".join(p.stem.split("_")[:2])
        root = ET.parse(SP / "lf_gt/maps" / f"{loc}.map").getroot()
        poly = []
        for tag in zone_tags:
            node = root.find(tag)
            if node is not None:
                poly = [tuple(map(int, pt.text.split(","))) for pt in node.findall("Point")]
                break
        zones[p.stem] = poly
    return dumps, answers, zones


def inside(x, y, poly):
    if len(poly) < 3:
        return False
    on = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            on = not on
    return on


def entered(box, poly, corners):
    x1, y1, x2, y2 = box
    if not inside((x1 + x2) / 2, y2, poly):
        return False
    if corners <= 0:
        return True
    pts = ((x1, y1), (x2, y1), (x1, y2), (x2, y2))
    return sum(inside(a, b, poly) for a, b in pts) >= corners


def intrusion_setup(dump_dir):
    dumps, answers, zones = load_person(dump_dir, "lf_gt/intrusion", ["Intrusion"])

    def alarm(name, combo):
        conf, corners, hold, settle = combo
        poly = zones[name]
        streak, entry, latest, last_new = {}, {}, None, None
        for r in dumps[name]:
            t, seen = r["t"], set()
            for b in r["boxes"]:
                if b[1] < conf or not entered(b[2:6], poly, corners):
                    continue
                seen.add(b[0])
                streak[b[0]] = streak.get(b[0], 0) + 1
                if streak[b[0]] == hold and b[0] not in entry:
                    entry[b[0]] = t
                    latest = t if latest is None else max(latest, t)
                    last_new = t
            for k in list(streak):
                if k not in seen:
                    streak[k] = 0
            if latest is not None and t - last_new >= settle:
                return latest
        return latest

    combos = [(c, n, h, s)
              for c in (0.25, 0.35, 0.45, 0.55)
              for n in (0, 3, 4)
              for h in (1, 2, 3)
              for s in (8.0, 12.0, 16.0, 20.0, 24.0, 28.0)]
    return list(dumps), alarm, combos, answers


def loiter_setup(dump_dir):
    dumps, answers, zones = load_person(dump_dir, "lf_gt/loiter", ["Loitering", "Intrusion"])
    step_seconds = 0.5

    def alarm(name, combo):
        conf, corners, dwell_s, delay, settle, gap = combo
        poly = zones[name]
        dwell, miss, entry, loiterers = {}, {}, {}, {}
        latest, last_new = None, None
        for r in dumps[name]:
            t, seen = r["t"], set()
            for b in r["boxes"]:
                if b[1] < conf or not entered(b[2:6], poly, corners):
                    continue
                seen.add(b[0])
                if dwell.get(b[0], 0) == 0:
                    entry[b[0]] = t
                dwell[b[0]] = dwell.get(b[0], 0) + step_seconds
                miss[b[0]] = 0
                if dwell[b[0]] >= dwell_s and b[0] not in loiterers:
                    loiterers[b[0]] = entry[b[0]]
                    latest = entry[b[0]] if latest is None else max(latest, entry[b[0]])
                    last_new = t
            for k in list(dwell):
                if k not in seen:
                    miss[k] = miss.get(k, 0) + 1
                    if miss[k] > gap:
                        dwell[k] = 0
            if latest is not None and t - last_new >= settle:
                return latest + delay
        return None if latest is None else latest + delay

    combos = [(c, n, d, dl, s, g)
              for c in (0.25, 0.4, 0.55)
              for n in (0, 3)
              for d in (6, 8, 10, 12)
              for dl in (8, 10, 12)
              for s in (0, 5, 10, 15)
              for g in (2, 6, 12)]
    return list(dumps), alarm, combos, answers


def fall_setup():
    d = np.load(SP / "deploy_track_logits.npz")
    names = sorted({k.split("__")[0] for k in d.files})
    curves = {n: [(d[f"{n}__t{i}"], d[f"{n}__z{i}"]) for i in range(int(d[f"{n}__n"][0]))]
              for n in names}
    answers = {n: float(d[f"{n}__gt"][0]) for n in names}

    def alarm(name, combo):
        th, need = combo
        onsets = []
        for t, z in curves[name]:
            run = 0
            for i in range(len(z)):
                run = run + 1 if z[i] >= th else 0
                if run >= need:
                    onsets.append(float(t[i - need + 1]))
                    break
        return min(onsets) if onsets else None

    combos = [(round(float(th), 2), n)
              for th in np.arange(-3.0, 3.01, 0.5) for n in (1, 2, 3, 4)]
    return names, alarm, combos, answers


def run(label, setup):
    names, alarm, combos, answers = setup
    full, best, loo, verdicts, picks = loocv(names, alarm, combos, answers)
    tp, fn, fp = tally(verdicts)
    print(f"\n===== {label} ({len(names)}편 · 조합 {len(combos)}개) =====")
    print(f"  전수 최고 (그 영상들 보고 고름) : {full:6.2f}   설정 {best}")
    print(f"  LOOCV    (가린 영상에 적용)     : {loo:6.2f}   정검 {tp} 미검 {fn} 오검 {fp}")
    top = Counter(picks.values()).most_common(1)[0]
    print(f"  가장 많이 뽑힌 설정: {top[0]} ({top[1]}/{len(names)}편)")
    bad = [n for n, v in zip(names, verdicts) if v != "정검"]
    print(f"  LOOCV 실패 {len(bad)}편: {bad}")
    return {"항목": label, "전수": full, "LOOCV": loo, "정검": tp, "미검": fn, "오검": fp,
            "전수설정": str(best), "최다선택": str(top[0]), "실패": bad}


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = []
    if which in ("all", "fire"):
        out.append(run("방화 (human_full)", fire_setup()))
    if which in ("all", "intrusion"):
        out.append(run("침입 (타일 덤프)", intrusion_setup("dump_intrusion_tile")))
    if which in ("all", "loiter"):
        out.append(run("배회 (기존 덤프)", loiter_setup("dump_loiter_trk_id")))
    if which in ("all", "fall"):
        out.append(run("쓰러짐 (트랙별)", fall_setup()))
    json.dump(out, open(SP / "loocv_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n===== 요약 =====")
    print(f"  {'항목':22s} {'전수':>7} {'LOOCV':>7}  차이")
    for r in out:
        print(f"  {r['항목']:22s} {r['전수']:7.2f} {r['LOOCV']:7.2f}  {r['LOOCV'] - r['전수']:+.2f}")

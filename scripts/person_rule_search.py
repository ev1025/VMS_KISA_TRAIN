# -*- coding: utf-8 -*-
# 기준: 판정을 다시 구현하지 않는다. _kisa_port/tools/kisa_items.py 의 IntrusionRule/LoiterRule 을
#       그대로 불러 쓴다. 처음에는 재구현했다가 gap 파라미터를 빠뜨려 85.71 이 나왔다(실측 94.74).
#       docs/EXPERIMENTS.md 4절 "판정 규칙을 찾는 법" 참고.
"""침입·배회 판정 규칙을 훑는다. 제출 도구의 판정기를 그대로 쓴다.

왜 지금 하나
    침입 94.74 · 배회 93.10 으로 합격선은 넘었지만 마진이 각각 한 편이다.
    한 편만 창 밖으로 나가면 배회는 89.66 으로 떨어진다.
    그런데 두 항목의 판정 상수는 손으로 정한 값이고 방화·쓰러짐과 달리 훑어본 적이 없다.

어떻게 하나
    추론은 하지 않는다. dumps/intrusion_tile_v2 · dumps/loiter_trk_id 에 저장된
    트랙 박스를 판정기에 먹여 시각만 다시 뽑는다. 조합 하나에 몇 초면 된다.

    판정기는 제출 도구의 것을 그대로 쓴다. 다시 구현하면 오늘처럼 어긋난다.
    (IntrusionRule 의 gap = 끊김 허용. 이게 빠지면 92.86 시절 로직이 된다.)

새로 시험하는 축
    지금 hold 는 "연속 hold 표본" 이고 gap 만큼 끊김을 봐준다.
    방화에서는 '3초 안에 4회'를 '5초 창에 3회'로 바꾸자 크게 좋아졌다. 검출이 띄엄띄엄 뜨기 때문이다.
    사람도 가림·자세로 끊기므로 gap 을 키우는 것이 같은 효과를 낸다. 그래서 gap 을 축에 넣는다.

사용
    python scripts/person_rule_search.py intrusion
    python scripts/person_rule_search.py loiter
"""
import json
import statistics as st
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_paths as KP           # noqa: E402
import kisa_items as K            # noqa: E402

BEFORE, AFTER = 2.0, 10.0


def gt_of(stem, item):
    for p in KP.videos(item).rglob(f"{stem}.xml"):
        al = ET.parse(p).getroot().find(".//Alarm")
        if al is None:
            return None
        h, m, s = (int(v) for v in al.findtext("StartTime").split(":"))
        return h * 3600 + m * 60 + s
    return None


def load(dump_dir, item, zone_tag):
    """덤프 한 편 = [{t, boxes:[[트랙,conf,x1,y1,x2,y2]]}...]. 영역은 제출 도구와 같은 함수로 읽는다."""
    out = []
    for p in sorted((V / "dumps" / dump_dir).glob("*.jsonl")):
        gt = gt_of(p.stem, item)
        if gt is None:
            continue
        rows = [json.loads(l) for l in p.read_text().splitlines()]
        poly = K.zone_of(KP.ZONE_MAPS, p.stem, zone_tag)
        out.append((p.stem, gt, rows, poly))
    return out


def run_intrusion(rows, poly, conf, corners, hold, settle, gap):
    j = K.IntrusionRule(poly, conf, corners, hold, settle, gap)
    for r in rows:
        j.feed(r["t"], r["boxes"])
    return j.final()


def run_loiter(rows, poly, conf, corners, dwell, settle, gap, step=0.5, delay=10.0):
    j = K.LoiterRule(poly, conf, corners, dwell, settle, gap, step)
    for r in rows:
        j.feed(r["t"], r["boxes"])
    o = j.final()
    return None if o is None else o + delay


def score(clips, fn, cfg):
    tp = fn_ = fp = 0
    det = []
    for stem, gt, rows, poly in clips:
        sa = fn(rows, poly, **cfg)
        if sa is None:
            v = "미검"; fn_ += 1
        elif gt - BEFORE <= sa <= gt + AFTER:
            v = "정검"; tp += 1
        else:
            v = "오검"; fn_ += 1; fp += 1
        det.append((stem, gt, sa, v))
    f1 = 200.0 * tp / (2 * tp + fn_ + fp) if tp else 0.0
    return f1, tp, fn_, fp, det


def main():
    item = sys.argv[1] if len(sys.argv) > 1 else "intrusion"
    cfg0 = dict(K.ITEMS["intrusion" if item == "intrusion" else "loitering"])
    if item == "intrusion":
        clips = load("intrusion_tile", "침입", cfg0["zone"])
        fn = run_intrusion
        now = dict(conf=cfg0["conf"], corners=cfg0["corners"], hold=cfg0["hold"],
                   settle=cfg0["settle"], gap=cfg0["gap"])
        grid = [dict(conf=c, corners=n, hold=h, settle=s, gap=g)
                for c in (0.30, 0.40, 0.45, 0.50, 0.55)
                for n in (0, 3, 4)
                for h in (1, 2, 3, 4)
                for s in (12.0, 18.0, 24.0, 30.0)
                for g in (0, 2, 4, 6, 8)]
    else:
        clips = load("loiter_trk_id", "배회", cfg0["zone"])
        fn = run_loiter
        now = dict(conf=cfg0["conf"], corners=cfg0["corners"], dwell=cfg0["dwell"],
                   settle=cfg0["settle"], gap=cfg0["gap"], step=cfg0["stride"])
        grid = [dict(conf=c, corners=cfg0["corners"], dwell=d, settle=s, gap=g, step=cfg0["stride"])
                for c in (0.30, 0.40, 0.50)
                for d in (3.0, 4.5, 6.0, 8.0, 10.0)
                for s in (3.0, 5.0, 8.0, 12.0)
                for g in (2, 4, 6, 8, 12)]

    print(f"{item} · {len(clips)}편 · 후보 {len(grid)}조합\n")
    f1, tp, fn_, fp, _ = score(clips, fn, now)
    print(f"지금 값 {now}")
    print(f"  -> {f1:.2f}  (정검 {tp} 미검 {fn_} 오검 {fp})")
    print("  ※ 이 값이 제출 경로 실측과 같아야 아래 스윕을 믿을 수 있다"
          " (침입 94.74 · 배회 93.10)\n")

    res = sorted(((score(clips, fn, c)[0], c) for c in grid), key=lambda x: -x[0])
    top = res[0][0]
    tied = [c for s, c in res if s >= top - 1e-9]
    print(f"최고 {top:.2f} · 동점 {len(tied)}/{len(grid)}개")
    for s, c in res[:6]:
        print(f"  {s:6.2f}  { {k: v for k, v in c.items() if k != 'step'} }")

    keys = [k for k, v in tied[0].items() if isinstance(v, (int, float)) and k != "step"]
    mid = {k: st.median([c[k] for c in tied]) for k in keys}
    best = min(tied, key=lambda c: sum(abs(c[k] - mid[k]) for k in keys))
    fb, tb, nb, pb, detb = score(clips, fn, best)
    print(f"\n동점 가운데: { {k: v for k, v in best.items() if k != 'step'} }")
    print(f"  -> {fb:.2f}  (정검 {tb} 미검 {nb} 오검 {pb})")

    tp2 = fn2 = fp2 = 0
    for i, held in enumerate(clips):
        rest = clips[:i] + clips[i + 1:]
        r = sorted(((score(rest, fn, c)[0], c) for c in grid), key=lambda x: -x[0])
        td = [c for s, c in r if s >= r[0][0] - 1e-9]
        m2 = {k: st.median([c[k] for c in td]) for k in keys}
        pick = min(td, key=lambda c: sum(abs(c[k] - m2[k]) for k in keys))
        _, a, b, c2, _ = score([held], fn, pick)
        tp2 += a; fn2 += b; fp2 += c2
    l1 = 200.0 * tp2 / (2 * tp2 + fn2 + fp2) if tp2 else 0.0
    print(f"  LOOCV {l1:.2f}  (정검 {tp2} 미검 {fn2} 오검 {fp2}) · 낙관 {fb - l1:+.2f}")

    print("\n못 맞힌 편 (동점 가운데)")
    for stem, gt, sa, v in detb:
        if v != "정검":
            print(f"  {stem}: {v} gt={gt} sa={sa} 창 [{gt-2}, {gt+10}]")


if __name__ == "__main__":
    main()

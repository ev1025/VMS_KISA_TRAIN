# -*- coding: utf-8 -*-
"""오프라인 재현이 실측과 맞는지 확인한다. 어긋나면 코드가 갈라진 것이다.

왜 있나 (2026-09-16)
    침입을 오프라인으로 재면 87.72 인데 제출 경로 실측은 94.74 였다.
    원인은 덤프를 만드는 person_redump.py 와 제출 경로의 NMS 인자(contain)가 달랐던 것인데,
    주석에는 "동일" 이라고 적혀 있어서 한참 헤맸다.
    주석은 거짓말을 할 수 있다. 이 스크립트는 실제로 계산해서 대조한다.

무엇을 보나
    results/BASELINE.json 의 실측값  대  덤프로 다시 계산한 값

    맞으면   그 항목의 오프라인 스윕 결과를 믿어도 된다.
    어긋나면 덤프를 만든 경로와 제출 경로가 갈라진 것이다. 스윕 결과를 쓰면 안 된다.

사용
    .venv/bin/python scripts/check_repro.py
    되돌아오는 값: 어긋난 항목이 있으면 1
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(V / "scripts"), str(V / "_kisa_port/tools"), str(V / "_kisa_port")]
import kisa_paths as KP           # noqa: E402
import kisa_items as K            # noqa: E402

BEFORE, AFTER = 2.0, 10.0
BASE = json.loads((V / "results/BASELINE.json").read_text(encoding="utf-8"))

# 항목 -> (덤프 후보들, 영상 폴더 이름, kisa_items 의 항목 키)
DUMPS = {
    # 살아 있는 덤프만 둔다. 옛 덤프는 dumps/_archive/2026-09-16/ 로 내렸다.
    # (제출 경로와 다른 방식으로 만들어져 재현이 어긋났다: 침입 87.72 · 배회 68.97)
    "침입": (["intrusion_tile_v3"], "침입", "intrusion"),
    "배회": (["loiter_botsort_v2"], "배회", "loitering"),
}


def gt_of(stem, item):
    for p in KP.videos(item).rglob(stem + ".xml"):
        al = ET.parse(p).getroot().find(".//Alarm")
        if al is None:
            return None
        h, m, s = (int(v) for v in al.findtext("StartTime").split(":"))
        return h * 3600 + m * 60 + s
    return None


def replay(dump_dir, item, key):
    """덤프를 제출 도구의 판정기에 먹여 점수를 다시 낸다. 판정은 다시 구현하지 않는다."""
    cfg = K.ITEMS[key]
    tp = fn = fp = 0
    for p in sorted((V / "dumps" / dump_dir).glob("*.jsonl")):
        gt = gt_of(p.stem, item)
        if gt is None:
            continue
        # 판정기는 제출 경로와 똑같이 make_judge 로 만든다.
        # 예전에는 여기서 직접 만들었는데, 규칙에 인자가 늘면 여기만 빠져도 기본값으로 조용히 통과했다.
        j = K.make_judge(key, cfg, p.stem, KP.ZONE_MAPS, None, None)
        delay = 0.0 if key == "intrusion" else cfg["delay"]
        for ln in p.read_text().splitlines():
            r = json.loads(ln)
            j.feed(r["t"], r["boxes"])
        o = j.final()
        sa = None if o is None else o + delay
        if sa is None:
            fn += 1
        elif gt - BEFORE <= sa <= gt + AFTER:
            tp += 1
        else:
            fn += 1; fp += 1
    f1 = 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0
    return round(f1, 2), tp, fn, fp


def main():
    bad = []
    print("실측(results/BASELINE.json) 대 덤프 재현\n")
    for item, (cands, vid, key) in DUMPS.items():
        ref = BASE["항목"].get(item)
        if not ref:
            continue
        print(f"  {item}  실측 {ref['점수']}  (정검 {ref['정검']} 미검 {ref['미검']} 오검 {ref['오검']})"
              f"  <- {ref['로그']}")
        hit = False
        for d in cands:
            if not (V / "dumps" / d).is_dir():
                continue
            f1, tp, fn, fp = replay(d, vid, key)
            ok = abs(f1 - ref["점수"]) < 0.01
            mark = "맞음" if ok else "어긋남"
            print(f"       {d:22s} {f1:6.2f}  (정검 {tp} 미검 {fn} 오검 {fp})  {mark}")
            hit = hit or ok
        if not hit:
            bad.append(item)
        print()

    for item in ("방화", "쓰러짐"):
        st = BASE["오프라인_재현_상태"].get(item) or {}
        print(f"  {item}  재현 상태: {'맞음' if st.get('맞음') else '미확인'}  ({st.get('도구')})")
        print(f"       이 두 항목은 전용 도구로 이미 대조했다. 실측 {BASE['항목'][item]['점수']}")

    print()
    if bad:
        print(f"어긋난 항목: {', '.join(bad)}")
        print("  덤프를 만든 경로와 제출 경로가 갈라졌다는 뜻이다.")
        print("  그 항목의 오프라인 스윕 결과를 쓰면 안 된다. docs/EXPERIMENTS.md 4.5절 참고.")
        return 1
    print("모두 맞음. 오프라인 스윕 결과를 써도 된다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

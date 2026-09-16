# -*- coding: utf-8 -*-
"""어떤 원본 데이터가 실제로 점수를 올렸나. 덤프 전부를 같은(배포) 규칙으로 다시 채점해
   그 실험이 쓴 데이터 구성과 나란히 놓는다."""
import json
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

C = K.ITEMS["fire"]
TL = V / "dumps/score_tl"


def sa_of(rows):
    q = deque(maxlen=C["win"])
    for t, f, s in rows:
        q.append((t, f >= C["fire"] or (f >= 0.3 and s >= C["smoke"])))
        if sum(1 for _, x in q if x) >= C["hits"]:
            return next(t0 for t0, x in q if x) + C["delay"]
    return None


def score_dump(name):
    d = json.loads((TL / (name + ".json")).read_text(encoding="utf-8"))
    pairs, miss = [], []
    for stem, e in sorted(d.items()):
        gt, sa = e["gt"], sa_of(e["rows"])
        pairs.append(([{"start_s": gt, "desc": "F"}],
                      [{"start_s": sa, "desc": "F"}] if sa is not None else []))
        if sa is None or not (gt - 2 <= sa <= gt + 10):
            miss.append(stem.replace("C00_", "").replace("_000", "_"))
    return K.score(pairs), miss, len(d)


rows = []
for f in sorted(TL.glob("*.json")):
    name = f.stem
    if name.startswith("_"):
        continue
    try:
        r, miss, n = score_dump(name)
    except Exception as e:
        print(f"  [건너뜀] {name}: {e!r}"); continue
    m = V / "results" / name / "meta.json"
    meta = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}
    tr = meta.get("train", {}) or {}
    rows.append({
        "name": name, "점수": r["점수"], "정검": r["정상검출"], "미검": r["미검출"],
        "오검": r["오검출"], "편수": n, "못잡음": miss,
        "model": meta.get("model", "?"), "imgsz": tr.get("imgsz", 640),
        "base": meta.get("base", "?"), "extras": meta.get("extras", []),
        "over": meta.get("oversample", {}), "n": meta.get("n_train"),
    })

rows.sort(key=lambda x: -x["점수"])
print(f"덤프 {len(rows)}개를 배포 규칙(불 {C['fire']} · 창 {C['win']} · {C['hits']}회)으로 재채점\n")
print(f"{'실험':<32}{'점수':>7}{'정검':>5}{'미검':>5}{'오검':>5}{'편':>4}  {'모델':<9}{'해상도':>6}  데이터")
for x in rows:
    ex = "+".join(e.replace("_yolo", "").replace("fasdd_", "F:") for e in x["extras"]) or "-"
    ov = "+".join(f"{k.replace('handset_', 'H:')}x{v}" for k, v in (x["over"] or {}).items()) or ""
    print(f"{x['name']:<32}{x['점수']:>7.2f}{x['정검']:>5}{x['미검']:>5}{x['오검']:>5}{x['편수']:>4}  "
          f"{x['model']:<9}{x['imgsz']:>6}  {x['base']} / {ex} {ov}")

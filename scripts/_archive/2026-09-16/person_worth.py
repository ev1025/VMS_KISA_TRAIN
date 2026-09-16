# -*- coding: utf-8 -*-
"""사람 실험별 데이터 구성과 침입·배회 점수."""
import json
from pathlib import Path

V = Path(__file__).resolve().parents[1]
print(f"{'실험':<34}{'모델':<9}{'해상도':>7}{'장수':>9}  데이터")
for m in sorted(V.glob("results/*/meta.json")):
    d = json.loads(m.read_text(encoding="utf-8"))
    if d.get("item") not in ("사람",) and not d.get("name", "").startswith("p"):
        continue
    if d.get("item") == "방화":
        continue
    t = d.get("train", {}) or {}
    ex = "+".join(d.get("extras", [])) or "-"
    ov = "+".join(f"{k}x{v}" for k, v in (d.get("oversample") or {}).items()) or "-"
    print(f"{d.get('name','?'):<34}{d.get('model','?'):<9}{t.get('imgsz', 640):>7}"
          f"{str(d.get('n_train')):>9}  {d.get('base','?')} / {ex} / {ov}")
    s = m.parent / "score.txt"
    if s.is_file():
        for ln in s.read_text(encoding="utf-8").splitlines():
            if "점수" in ln:
                print("       ", ln.strip())
    else:
        print("        (채점 없음)")

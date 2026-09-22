# -*- coding: utf-8 -*-
"""손라벨 학습셋 두 판의 내역을 나란히."""
import json
from pathlib import Path

V = Path(__file__).resolve().parents[1]
print(f"{'학습셋':<34}{'합계':>8}{'손라벨':>8}{'SAM전파':>9}{'하드네거':>9}")
for name in ("handset_person_20260915", "handset_person_20260916", "handset_person"):
    f = V / "data/학습데이터" / name / "meta.json"
    if not f.is_file():
        print(f"  {name:<32} 없음"); continue
    m = json.loads(f.read_text(encoding="utf-8"))
    s = m.get("stats", {}) or {}
    tot = (m.get("train") or 0) + (m.get("val") or 0)
    print(f"{name:<34}{tot:>8}{s.get('영상프레임:hand', 0):>8}"
          f"{s.get('영상프레임:sam', 0):>9}{s.get('하드네거티브', 0):>9}")

print()
print("실험이 무엇을 썼나")
for exp in ("p1280_coco_kisa_s_20260915", "p960_coco_hand_20260916"):
    f = V / "results" / exp / "meta.json"
    over = "(아직 안 돌아 meta 없음)"
    if f.is_file():
        over = json.loads(f.read_text(encoding="utf-8")).get("oversample")
    else:
        import yaml
        q = yaml.safe_load((V / "configs/queue_res1280_20260915.yaml").read_text(encoding="utf-8"))
        e = [x for x in q["experiments"] if x["name"] == exp]
        if e:
            over = e[0].get("oversample")
    print(f"  {exp:<32} {over}")

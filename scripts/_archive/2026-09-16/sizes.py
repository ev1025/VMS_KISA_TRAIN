# -*- coding: utf-8 -*-
"""방화 실험별 학습 장수·베이스 비율. 무엇을 빼면 얼마나 줄어드나."""
import json
from pathlib import Path

V = Path(__file__).resolve().parents[1]
NAMES = ["fresh_24k_base_20260909", "fresh_48k_base_20260909", "fresh_48k_fasdd_20260909",
         "fresh_48k_snowfull_20260909", "fresh_48k_azimjaan_20260909",
         "fresh_48k_wildpos_20260909", "fresh_48k_wildall_20260909",
         "g_base25_20260912", "g_base50_20260912", "g_wildpos_20260912", "g_noazim_20260912",
         "g_dfire_20260912", "s2_s640_20260913", "s2_s960_20260913",
         "f960_best_s_20260915", "f1280_best_s_20260915"]
print(f"{'실험':<32}{'장수':>9}{'base비율':>9}{'해상도':>7}  extras")
for n in NAMES:
    p = V / "results" / n / "meta.json"
    if not p.is_file():
        print(f"{n:<32}  (meta 없음)"); continue
    d = json.loads(p.read_text(encoding="utf-8"))
    t = d.get("train", {}) or {}
    ex = ", ".join(d.get("extras", [])) or "-"
    print(f"{n:<32}{str(d.get('n_train')):>9}{str(d.get('base_frac')):>9}"
          f"{t.get('imgsz', 640):>7}  {ex}")

print()
print("=== 학습 데이터 폴더 크기 ===")
for d in sorted((V / "data/학습데이터").iterdir()):
    if not d.is_dir():
        continue
    img = d / "images"
    if img.is_dir():
        n = sum(1 for _ in img.rglob("*.jpg")) + sum(1 for _ in img.rglob("*.png"))
        if n:
            print(f"  {d.name:<36}{n:>9}장")

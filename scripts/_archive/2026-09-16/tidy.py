# -*- coding: utf-8 -*-
"""오늘 만든 스크립트를 규칙에 맞게 정리한다.
   1) 절대경로 하드코딩을 파일 기준 상대경로로 바꾼다 (docs/file_path.md §1)
   2) 일회성 탐색 스크립트는 scripts/_archive/<날짜>/ 로 내린다 (§2)
"""
import re
import shutil
from pathlib import Path

V = Path(__file__).resolve().parents[1]
S = V / "scripts"
ARC = S / "_archive" / "2026-09-16"

# 계속 쓸 것 = scripts/ 에 남긴다
KEEP = {
    "fire_ens_try.py":  "가중치 조합별 방화 점수. f960 끝나면 바로 쓴다",
    "fragile.py":       "표본 하나를 빼면 판정이 깨지는가(취약성)",
    "early_late.py":    "SA 가 정답보다 이른가 늦은가 · 창 여유",
    "data_worth.py":    "덤프 전부를 배포 규칙으로 재채점 + 데이터 구성 대조",
    "leak_check.py":    "채점셋 라벨이 학습셋에 섞였는가",
    "label_state.py":   "손라벨·전파 현황과 학습셋 반영 여부",
    "sam_state.py":     "SAM2 전파 산출물 현황",
    "conf_sweep.py":    "침입 신뢰도 문턱 전수 스윕",
    "gt_check.py":      "원본 GT 시각이 맞는지 영상으로 확인",
    "show_fire.py":     "그 시각에 무엇을 불로 봤는지 상자로",
    "cancel.py":        "대기 중인 실험 취소 표시",
}
# 한 번 쓰고 결론 난 것 = 보관
ARCHIVE = ["why_miss.py", "why_miss2.py", "draw_zone.py", "smoke_look.py", "smoke_rel.py",
           "trace195.py", "recheck195.py", "why089.py", "person_worth.py", "sizes.py",
           "rescore_hand.sh"]

ABS = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
FIX = 'Path(__file__).resolve().parents[1]'

print("== 절대경로 → 파일 기준 상대경로")
for f in sorted(S.glob("*.py")):
    t = f.read_text(encoding="utf-8")
    if ABS not in t:
        continue
    n = t.count(ABS)
    t2 = t.replace(f'V = Path("{ABS}")', f"V = {FIX}")
    t2 = t2.replace(f'Path("{ABS}")', FIX)
    t2 = t2.replace(f'V = Path(r"{ABS}")', f"V = {FIX}")
    left = t2.count(ABS)
    f.write_text(t2, encoding="utf-8")
    print(f"   {f.name:<24} {n}곳 중 {n-left}곳 고침" + ("  <-- 남음, 손봐야 함" if left else ""))

print()
print("== 보관(scripts/_archive/2026-09-16/)")
ARC.mkdir(parents=True, exist_ok=True)
for name in ARCHIVE:
    p = S / name
    if p.is_file():
        shutil.move(str(p), str(ARC / name))
        print(f"   {name}")

(ARC / "README.md").write_text(
    "# 2026-09-16 일회성 탐색 스크립트\n\n"
    "그날 결론을 내고 문서에 옮긴 뒤 내린 것들이다. 결론은 아래에 있다.\n\n"
    "- `why_miss*.py` · `draw_zone.py` — 침입 미검 3편 원인(검출 한계) → `docs/EXPERIMENTS.md` 4.11\n"
    "- `smoke_look.py` · `smoke_rel.py` — 연기를 알고리즘으로 살릴 수 있나(안 됨) → 4.12\n"
    "- `trace195.py` · `recheck195.py` · `why089.py` — 방화 앙상블 취약성 → 4.13\n"
    "- `person_worth.py` · `sizes.py` — 사람 실험 구성·학습셋 크기 조사\n"
    "- `rescore_hand.sh` — 손라벨 단독 사람 가중치 재채점(1회)\n\n"
    "계속 쓰는 도구는 `scripts/` 에 남아 있다. `fire_ens_try.py` · `fragile.py` · "
    "`early_late.py` · `data_worth.py` · `leak_check.py` · `label_state.py` 등.\n",
    encoding="utf-8")

print()
print("== scripts/ 에 남긴 것")
for k, why in KEEP.items():
    mark = "있음" if (S / k).is_file() else "없음!"
    print(f"   {k:<22}{mark}  {why}")

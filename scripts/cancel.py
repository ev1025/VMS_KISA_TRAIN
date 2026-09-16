# -*- coding: utf-8 -*-
"""대기 중인 실험을 취소 표시한다. 도는 학습은 건드리지 않는다."""
from pathlib import Path

V = Path(__file__).resolve().parents[1]
WHY = {
 "s2_m960_20260913":
   "yolo11m. 640 에서 m/l/x 가 전부 88.89 로 평평했고 s@960 이 94.74 로 더 높다. 모델을 키울 이유가 없다.",
 "p1280_hand_s_20260915":
   "학습 해상도 1280. 방화에서 1280 은 77.78 로 실패했고 배포는 침입 960 타일 · 배회 640 이다. 960 으로 다시 짠다.",
 "p960_coco_kisa_s_20260915":
   "취소 아님. 순서를 바꾸려고 이 큐에서 내린다. 손라벨 검증이 끝난 뒤 새 큐에서 돌린다.",
 "p960_hand_s_20260915":
   "취소 아님. 순서를 바꾸려고 이 큐에서 내린다. 손라벨 단독 검증이라 1순위로 올려 새 큐에서 돌린다.",
}
for name, why in WHY.items():
    d = V / "results" / name
    d.mkdir(parents=True, exist_ok=True)
    f = d / "score.txt"
    if f.is_file():
        print(f"  {name}: 이미 결과가 있다. 건드리지 않는다"); continue
    f.write_text(f"=== {name} ===\n(돌리지 않음 · 2026-09-16)\n{why}\n", encoding="utf-8")
    print(f"  {name}: 취소 표시함")

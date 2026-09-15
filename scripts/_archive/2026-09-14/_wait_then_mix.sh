#!/bin/bash
# 방화 큐(모델 크기 비교 4잡 + 진행 2잡)가 끝나면 → 방화 그리드 1단계(14잡, 2잡 동시) → 사람/방화 혼합 큐(5잡, 2잡 동시) 순서로 자동 실행.
# 저장소 루트는 스크립트 위치에서 구한다(경로를 박아 넣지 않는다 · docs/file_path.md 1절).
cd "${VMS_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}" || exit 1
PY=.venv/bin/python
while pgrep -f '[e]xp_queue.py run configs/queue_fire_20260909' >/dev/null; do sleep 300; done
echo "[$(TZ=Asia/Seoul date '+%m-%d %H:%M KST')] 방화 큐 종료 → 그리드 1단계 시작" >> logs/queue/runner_grid.log
$PY scripts/exp_queue.py run configs/queue_grid_fire_20260912.yaml --jobs 2 >> logs/queue/runner_grid.log 2>&1
echo "[$(TZ=Asia/Seoul date '+%m-%d %H:%M KST')] 그리드 종료 → 혼합 큐 시작" >> logs/queue/runner_mix.log
exec $PY scripts/exp_queue.py run configs/queue_mix_20260911.yaml --jobs 2 >> logs/queue/runner_mix.log 2>&1

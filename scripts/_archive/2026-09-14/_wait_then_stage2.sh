#!/bin/bash
# 그리드 1단계 → 혼합 큐가 모두 끝나면 방화 2단계 큐를 시작한다.
# 그리드→혼합 은 _wait_then_mix.sh 가 exec 로 넘기므로 교대 순간 둘 다 잠깐 안 보인다.
# 그 순간을 종료로 오인하지 않도록, 둘 다 없는 상태가 연속 3번(3분) 확인될 때만 시작한다.
# 오케스트레이터는 항상 하나만 돌게 한다(러너를 새로 띄우면 kill_orphan_trainers 가 도는 학습을 죽인다).
# 저장소 루트는 스크립트 위치에서 구한다(경로를 박아 넣지 않는다 · docs/file_path.md 1절).
cd "${VMS_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}" || exit 1
PY=.venv/bin/python
GRID='[e]xp_queue.py run configs/queue_grid_fire_20260912'
MIX='[e]xp_queue.py run configs/queue_mix_20260911'

gone=0
while [ "$gone" -lt 3 ]; do
  if pgrep -f "$GRID" >/dev/null || pgrep -f "$MIX" >/dev/null; then
    gone=0
  else
    gone=$((gone + 1))
  fi
  sleep 60
done

echo "[$(TZ=Asia/Seoul date '+%m-%d %H:%M KST')] 그리드·혼합 종료 → 방화 2단계 시작" >> logs/queue/runner_stage2.log
exec $PY scripts/exp_queue.py run configs/queue_stage2_fire_20260913.yaml --jobs 2 >> logs/queue/runner_stage2.log 2>&1

#!/bin/bash
# 큐 순차 실행: 혼합(사람 남은 2잡) → 방화 2단계(6잡). 각 큐 안에서 2잡 동시.
# 러너는 results/<실험>/score.txt 가 있는 실험을 건너뛰므로 이미 끝난 것은 다시 돌지 않는다.
# 오케스트레이터는 항상 하나만 살아 있게 한다. 러너를 새로 띄우면 kill_orphan_trainers 가
# 돌고 있는 학습을 죽이므로, 이 스크립트를 두 번 띄우지 않는다.
# 저장소 루트는 스크립트 위치에서 구한다(경로를 박아 넣지 않는다 · docs/file_path.md 1절).
cd "${VMS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}" || exit 1
PY=.venv/bin/python
mkdir -p logs/queue

stamp() { TZ=Asia/Seoul date '+%m-%d %H:%M KST'; }

echo "[$(stamp)] 혼합 큐 시작" >> logs/queue/runner_mix.log
$PY scripts/exp_queue.py run configs/queue_mix_20260911.yaml --jobs 2 >> logs/queue/runner_mix.log 2>&1

echo "[$(stamp)] 혼합 큐 종료 → 방화 2단계 시작" >> logs/queue/runner_stage2.log
$PY scripts/exp_queue.py run configs/queue_stage2_fire_20260913.yaml --jobs 2 >> logs/queue/runner_stage2.log 2>&1

echo "[$(stamp)] 2단계 종료 → 고해상도(1280) 큐 시작" >> logs/queue/runner_res1280.log
exec $PY scripts/exp_queue.py run configs/queue_res1280_20260915.yaml --jobs 2 >> logs/queue/runner_res1280.log 2>&1

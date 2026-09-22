#!/bin/bash
# 대조군 C 가 끝나면 손라벨 3벌을 최신판으로 다시 만들고 큐를 이어 돌린다.
#
# 왜 필요한가 (2026-09-22)
#   C 가 도는 중에 데이터셋 폴더를 덮으면 도는 학습이 파일을 잃고 깨진다.
#   그렇다고 그냥 두면 러너가 이미 잡아 둔 정의로 1~6번도 옛 라벨로 돈다
#   (러너는 yaml 을 다시 읽지만 '새 이름' 만 집어 간다).
#   그래서 C 의 채점이 끝난 뒤에 러너를 멈추고, 다시 만들고, 다시 띄운다.
#   C 는 score.txt 가 있어 건너뛴다.
V=/NHNHOME/WORKSPACE/26mss002_E3/vms
cd "$V" || exit 1
CTRL=f960_single_x2_20260922
say() { echo "[$(TZ=Asia/Seoul date '+%m-%d %H:%M KST')] $*"; }

say "대조군 $CTRL 채점 끝나기를 기다린다"
until [ -f "results/$CTRL/score.txt" ]; do sleep 120; done
say "채점 끝. 러너를 멈춘다"

tmux kill-session -t firetier 2>/dev/null
sleep 5
# 러너를 죽이면 학습 자식이 고아로 남아 GPU 를 붙들고 있다(09-22 실측 174GB).
for p in $(pgrep -f 'resume_train'); do kill -9 "$p" 2>/dev/null; done
sleep 10
say "GPU $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"

say "손라벨 3벌 재빌드(최신 라벨 3,837행)"
for a in "hand:handset_fire_hand_20260922" "prop:handset_fire_prop_20260922" ":handset_fire_all_20260922"; do
  m=${a%%:*}; n=${a##*:}
  rm -rf "data/학습데이터/$n"
  if [ -n "$m" ]; then
    .venv/bin/python scripts/build_trainset.py fire --no-gt --marks "$m" --neg 5 --name "$n" 2>&1 | tail -2
  else
    .venv/bin/python scripts/build_trainset.py fire --no-gt --neg 5 --name "$n" 2>&1 | tail -2
  fi
done

say "누수 확인"
.venv/bin/python scripts/leak_check.py 2>&1 | grep -E 'handset_fire_(hand|prop|all)_20260922|오염된 학습셋 없음'

say "큐 재개 (C 는 건너뛴다)"
tmux new-session -d -s firetier \
  ".venv/bin/python scripts/exp_queue.py run configs/queue_fire_tier_20260922.yaml --jobs 1 2>&1 | tee -a logs/queue/runner_fire_tier.log"
sleep 20
tail -3 logs/queue/runner_fire_tier.log
say "끝"

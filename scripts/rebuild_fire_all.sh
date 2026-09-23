#!/bin/bash
# 방화 학습 데이터를 지금 손라벨 기준으로 처음부터 다시 만든다 (2026-09-23).
#
# 순서가 중요하다. 손라벨 -> handset 3벌 -> 안개 합성(handset_all 에서 파생).
# 순서를 어기면 파생 세트가 옛 스냅샷을 물어 같은 프레임에 정답이 두 개가 된다.
# 2026-09-23 에 그렇게 해서 f960_tier42_base 가 63.16 으로 떨어졌다(충돌 1,141프레임).
#
# 끝나면 scripts/queue_check.py 로 확인하고 큐를 돌린다.
cd /NHNHOME/WORKSPACE/26mss002_E3/vms || exit 1
PY=/NHNHOME/WORKSPACE/26mss002_E3/vms/.venv/bin/python
set -e
set -x
"$PY" scripts/build_trainset.py fire --name handset_fire_hand_20260923 --no-gt --marks hand
"$PY" scripts/build_trainset.py fire --name handset_fire_prop_20260923 --no-gt --marks prop
"$PY" scripts/build_trainset.py fire --name handset_fire_all_20260923 --no-gt
"$PY" scripts/fog_aug.py --src handset_fire_all_20260923 --name fire_mask_hn_fog_20260923
set +x
echo "=== 다 만들었다. 이제 검사 ==="
"$PY" scripts/queue_check.py configs/queue_fire_20260923.yaml

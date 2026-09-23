#!/bin/bash
# 중복 박스를 지운 손라벨(2026-09-23)로 방화 학습셋 세 벌을 다시 만든다.
# 09-22 판은 옛 라벨로 만든 것이라 같은 불에 두 번 친 박스가 들어 있다.
# 이름을 새로 주므로 지금 도는 큐(09-22 판 사용)는 영향을 안 받는다.
cd /NHNHOME/WORKSPACE/26mss002_E3/vms || exit 1
PY=.venv/bin/python
set -x
$PY scripts/build_trainset.py fire --name handset_fire_hand_20260923 --no-gt --marks hand
$PY scripts/build_trainset.py fire --name handset_fire_prop_20260923 --no-gt --marks prop
$PY scripts/build_trainset.py fire --name handset_fire_all_20260923 --no-gt

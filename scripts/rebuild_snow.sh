#!/bin/bash
# 눈 배경 합성을 다시 만든다. 배경을 9편 -> 15편(불 얹는 눈 배경 5 -> 7)으로 늘린 뒤.
cd /NHNHOME/WORKSPACE/26mss002_E3/vms || exit 1
PY=/NHNHOME/WORKSPACE/26mss002_E3/vms/.venv/bin/python
set -e
set -x
$PY scripts/fire_paste.py --name fire_snowbg_흑백불_20260923 --n-out 2400 --불종류 흑백
$PY scripts/fire_paste.py --name fire_snowbg_작은불_20260923 --n-out 2400 --불종류 컬러 --크기 작게
set +x
echo '=== 검사 ==='
$PY scripts/queue_check.py configs/queue_fire_20260923.yaml

#!/bin/bash
# 방화 오경보 덤프를 차례로 뜬다. GPU 를 하나씩만 쓴다(학습이 같이 돌고 있다).
# 순서는 값어치 순. 기준선이 가장 성능이 좋으므로 기준선부터 넓게 본다.
cd /NHNHOME/WORKSPACE/26mss002_E3/vms || exit 1
PY=.venv/bin/python
B=runs/f960_mask_hn_x2_fog3_20260920/yolo11s/weights/best.pt

wait_free() { while pgrep -f 'scripts/fire_fp_test.py' > /dev/null; do sleep 60; done; }

wait_free
echo "[1/3] 기준선 · 사람영상 200편"
$PY scripts/fire_fp_test.py $B --imgsz 960 --tiles --pool 사람 --max 200 \
    --tag mask_hn_x2_fog3_person > logs/queue/fire_fp_baseline_person.log 2>&1

echo "[2/3] tier42 · 악천후 45편"
$PY scripts/fire_fp_test.py runs/f960_tier42_20260922/yolo11s/weights/best.pt \
    --imgsz 960 --tiles --tag tier42 > logs/queue/fire_fp_tier42.log 2>&1

echo "[3/3] C single_x2 · 악천후 45편"
$PY scripts/fire_fp_test.py runs/f960_single_x2_20260922/yolo11s/weights/best.pt \
    --imgsz 960 --tiles --tag single_x2 > logs/queue/fire_fp_single_x2.log 2>&1

echo 전부 끝

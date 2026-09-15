#!/bin/bash
# 채점이 안 돌아간 실험 두 개를 채운다. GPU 여유가 크므로 동시에 돌린다.
#   person_hand_20260910  손라벨 미세조정(사람) → kisa_items 로 침입·배회
#   g_nofasdd_20260912    방화 → score_kisa
cd "${VMS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}" || exit 1
PY=.venv/bin/python

$PY score_hand.py > logs/queue/val_person_hand.log 2>&1 &
P1=$!

$PY score_kisa.py runs/g_nofasdd_20260912/yolo11s/weights/best.pt \
    --videos "data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포" \
    --gt "data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포" \
    --stride 0.5 --imgsz 640 --tiles \
    > results/g_nofasdd_20260912/score.txt 2>logs/queue/val_g_nofasdd.log &
P2=$!

wait $P1; echo "[person_hand] 종료 $?"
wait $P2; echo "[g_nofasdd] 종료 $?"

#!/bin/bash
# 큐(학습)가 다 끝나면 쓰러짐 330편 확장 평가를 시작한다.
# 학습과 GPU 를 다투지 않게 순서를 지킨다. 편마다 파일을 쓰므로 중간에 끊겨도 다시 돌리면 이어진다.
cd /NHNHOME/WORKSPACE/26mss002_E3/vms
while pgrep -f '[m]odel.py train' > /dev/null; do sleep 300; done
sleep 60
echo "[$(date +'%m-%d %H:%M')] 학습이 모두 끝났다. 쓰러짐 330편 확장 평가 시작"
.venv/bin/python scripts/fall_dump_all.py --out dumps/fall_seq_dev330
echo "[$(date +'%m-%d %H:%M')] 덤프 끝. 규칙 훑기"
.venv/bin/python scripts/fall_sweep.py dumps/fall_seq_dev330

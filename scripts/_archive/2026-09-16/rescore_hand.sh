#!/bin/bash
# 손라벨 단독 사람 가중치(09-11)를 배포 경로로 다시 채점한다.
#   침입 = 3x3 타일 @960 · 배회 = 전체프레임 @640 (배포 구성)
# 주의: --person-weights 는 절대경로여야 한다. 상대경로면 WEIGHTS/ 가 앞에 붙어 못 찾는다.
cd /NHNHOME/WORKSPACE/26mss002_E3/vms
V=$PWD
W="$V/runs/person_kisa_only_s_20260911/yolo11s/weights/best.pt"
D="$V/data/원본데이터/kisa_배포_검증영상/deploy_val"
M="$V/data/원본데이터/kisa_배포_검증영상/zone_maps"
mkdir -p /tmp/rescore_hand
echo "[시작] $(date '+%F %T')  가중치 $W"
for pair in "loitering:배회(30개):640" "intrusion:침입(30개):960"; do
  it=${pair%%:*}; rest=${pair#*:}; dir=${rest%%:*}; z=${rest##*:}
  echo "--- $it (해상도 $z) $(date '+%T')"
  .venv/bin/python _kisa_port/tools/kisa_items.py --item "$it" \
    --videos "$D/$dir/배포" --gt "$D/$dir/배포" --maps "$M" \
    --out "/tmp/rescore_hand/$it" --person-weights "$W" --person-imgsz "$z" 2>&1 \
    | grep -E "^\[$it\]|^  클립"
done
echo "[끝] $(date '+%F %T')"

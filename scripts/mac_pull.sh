#!/bin/bash
# 맥북에 라벨·학습에 필요한 것을 서버에서 받는다.
#
# 왜 있나 (2026-09-22)
#   집 IP 는 NHN 방화벽에 없어서 B200 에 못 붙는다. 사무실에 있을 때(회사 IP) 한 번에 받아 두고
#   집에서는 맥북 단독으로 돌린다. 여러 명령을 따로 치다 빠뜨리는 것을 막으려고 하나로 묶었다.
#
# 쓰는 법 (사무실에서, 저장소 뿌리에서)
#   ./scripts/mac_pull.sh 라벨          손라벨만 (30MB)  — 라벨 작업용
#   ./scripts/mac_pull.sh 학습          + 학습셋 (4.5GB) — 학습까지 해보려면
#   ./scripts/mac_pull.sh 학습 --베이스  + aihub71751_48k (15GB 더)
#   ./scripts/mac_pull.sh 영상 악천후    + 영상 45편 (12GB)
#   ./scripts/mac_pull.sh 영상 방화      + 영상 75편 (24GB)
#
# rsync 라 중간에 끊겨도 다시 돌리면 이어받는다.
set -u
SRV="${SRV_HOST:-nhn-yolo}"
ROOT="${SRV_ROOT:-/NHNHOME/WORKSPACE/26mss002_E3/vms}"
R="$SRV:$ROOT"
MODE="${1:-라벨}"

cd "$(dirname "$0")/.." || exit 1
command -v rsync >/dev/null || { echo "rsync 가 없습니다"; exit 1; }

say() { echo; echo "── $* ──"; }
pull() {   # pull <서버 상대경로> <받을 자리>
  mkdir -p "$2"
  rsync -a --info=progress2 --partial "$R/$1" "$2/" || { echo "  실패: $1"; return 1; }
}

say "서버 연결 확인"
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$SRV" true 2>/dev/null; then
  echo "  $SRV 에 못 붙습니다."
  echo "  사무실(회사 IP)에서 실행하세요. 집 IP 는 NHN 방화벽에 없습니다."
  exit 1
fi
echo "  연결됨"

say "손라벨 (30MB)"
pull "data/학습데이터/손라벨" "data/학습데이터"
pull "data/학습데이터/자동라벨" "data/학습데이터" 2>/dev/null || true
pull "configs/datasets.yaml" "configs"

if [ "$MODE" = "학습" ]; then
  say "사전학습 가중치"
  pull "model/pretrained/yolo11s.pt" "model/pretrained"

  say "학습셋 (약 4.5GB)"
  for n in fasdd_snowfog wildfire_fog_neg wildfire_pos_yolo fasdd_yolo \
           handset_fire_hand_20260922 handset_fire_prop_20260922 \
           handset_fire_all_20260922 fire_mask_hn_fog_20260919; do
    echo "  $n"
    pull "data/학습데이터/$n" "data/학습데이터"
  done

  if [ "${2:-}" = "--베이스" ]; then
    say "베이스 aihub71751_48k (15GB)"
    pull "data/원본데이터/aihub71751_48k" "data/원본데이터"
  else
    echo
    echo "  베이스(aihub71751_48k, 15GB)는 받지 않았습니다."
    echo "  손라벨 중심으로 경향만 볼 거면 없어도 됩니다. 받으려면 --베이스 를 붙이세요."
  fi
fi

if [ "$MODE" = "영상" ]; then
  case "${2:-}" in
    악천후) CAT=KISA_악천후_사람 ;;
    방화)   CAT=kisa_연구개발_방화영상 ;;
    *) echo "  영상 뒤에 악천후 또는 방화 를 적으세요"; exit 1 ;;
  esac
  say "영상 $CAT"
  pull "data/원본데이터/$CAT" "data/원본데이터"
fi

say "받은 것"
du -sh data/학습데이터/* data/원본데이터/* model/pretrained/* 2>/dev/null | sort -h | tail -12
echo
echo "채점셋이 섞이지 않았는지 확인하려면:  python3 scripts/leak_check.py"

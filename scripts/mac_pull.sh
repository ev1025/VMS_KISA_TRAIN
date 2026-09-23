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
#   ./scripts/mac_pull.sh 사람          사람 학습셋 + 검증셋 (약 3.5GB) - 침입·배회 악천후 시험
#   ./scripts/mac_pull.sh 사람 --베이스  + trainset_person_20260915 에서 COCO 를 뺀 것 (254MB 더)
#   ./scripts/mac_pull.sh 채점 침입     채점 영상 30편 + 영역파일 (6.6GB · 15분)
#   ./scripts/mac_pull.sh 채점 배회     채점 영상 30편 + 영역파일 (7.7GB · 18분)
#   ./scripts/mac_pull.sh 채점 전부     침입 + 배회 (14.3GB · 33분)
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

if [ "$MODE" = "사람" ]; then
  # 사람(침입·배회) 학습셋.
  # 맥북에서 할 일은 "악천후 20편을 넣으면 못 풀던 편이 풀리나" 를 보는 것이다(docs/맥북_작업.md 4번).
  # 서버 학습은 117,529장을 1280 으로 돌린다. 맥북으로 재현할 수 없다.
  say "사전학습 가중치"
  pull "model/pretrained/yolo11s.pt" "model/pretrained"

  say "사람 손라벨 학습셋 (약 3.2GB) - 악천후 20편 포함"
  for n in person_mask_hn_20260923 person_mask_hn_20260918; do
    if ssh "$SRV" "test -d '$ROOT/data/학습데이터/$n'" 2>/dev/null; then
      echo "  $n"
      pull "data/학습데이터/$n" "data/학습데이터"
      break
    fi
  done

  say "검증셋 (386MB)"
  pull "data/학습데이터/evalset_person" "data/학습데이터"

  if [ "${2:-}" = "--베이스" ]; then
    # COCO 는 공개 데이터라 맥북에서 직접 받으면 된다. 19GB 중 우리 자료는 254MB 뿐이다.
    say "베이스 trainset_person_20260915 에서 COCO 를 뺀 것 (약 254MB)"
    echo "  COCO(images_train2017_*) 117,266장은 받지 않는다. KISA 영상 프레임 1,528장만 받는다"
    B=data/학습데이터/trainset_person_20260915
    mkdir -p "$B"
    rsync -aL --info=progress2 --partial --exclude 'images_train2017_*' \
      "$R/data/학습데이터/trainset_person_20260915/" "$B/" || echo "  실패: 베이스"

    # 목록에서 COCO 줄을 지운다. 없는 파일이 목록에 남으면 ultralytics 가 죽는다.
    for f in train.txt val.txt; do
      if [ -f "$B/$f" ]; then
        before=$(wc -l < "$B/$f")
        grep -v 'images_train2017_' "$B/$f" > "$B/$f.tmp" && mv "$B/$f.tmp" "$B/$f"
        echo "  $f  $before줄 -> $(wc -l < "$B/$f")줄 (COCO 줄 삭제)"
      fi
    done
    echo "  COCO 를 넣고 싶으면 맥북에서 train2017 을 직접 받아 넣는다(docs/맥북_작업.md 4번)"
  else
    echo
    echo "  베이스(trainset_person_20260915)는 받지 않았습니다."
    echo "  악천후 효과를 보는 데는 없어도 됩니다. 받으려면 --베이스 를 붙이세요(COCO 빼고 254MB)."
  fi
fi

if [ "$MODE" = "채점" ]; then
  # 침입·배회 F1 을 실제로 재려면 채점 영상과 영역 파일이 있어야 한다.
  # 이미지 mAP(evalset_person)만으로는 점수가 안 나온다.
  #
  # 이 영상은 채점 전용이다. configs/datasets.yaml 에 use: eval 로 박혀 있어
  # 학습셋 빌더가 자동으로 뺀다. 어떤 경우에도 학습에 넣지 않는다.
  BASE="data/원본데이터/kisa_배포_검증영상"
  say "영역 파일 (.map 296개) - 침입·배회 필수"
  pull "$BASE/zone_maps" "$BASE"

  case "${2:-}" in
    침입) CATS="침입(30개)" ;;
    배회) CATS="배회(30개)" ;;
    전부) CATS="침입(30개) 배회(30개)" ;;
    *) echo "  채점 뒤에 침입 · 배회 · 전부 중 하나를 적으세요"; exit 1 ;;
  esac

  for c in $CATS; do
    say "채점 영상 $c"
    pull "$BASE/deploy_val/$c" "$BASE/deploy_val"
  done
  echo
  echo "  채점 돌리는 법은 docs/맥북_작업.md 4번 '점수를 재려면' 을 보세요."
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

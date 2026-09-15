#!/bin/bash
# 방화 큐(queue3) 끝나면 나머지 3항목 채점 → 결과 탭에 F1 표시.
# 3항목은 이미 모델/특징 있음 → 재학습 아니라 검증영상 채점(추론)만.
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
DV="$V/data/원본데이터/kisa_배포_검증영상/deploy_val"
MAPS="$V/data/원본데이터/kisa_배포_검증영상/zone_maps"
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
log "queue3(방화) 종료 대기"
while tmux has-session -t queue3 2>/dev/null; do sleep 120; done

cd $V
# 인자: item  검증영상폴더  (maps 쓰면 1)
run_item(){
  local ITEM=$1 VID="$2" USEMAP=$3
  local OUT=$V/dumps/sa_$ITEM
  [ -s "$V/results/$ITEM.txt" ] && { log "$ITEM 결과 존재, 건너뜀"; return; }
  rm -rf "$OUT"; mkdir -p "$OUT"
  log "$ITEM 예측(sa_runner)"
  if [ "$USEMAP" = "1" ]; then
    CUDA_VISIBLE_DEVICES=0 $PY $V/scripts/sa_runner.py --item $ITEM --videos "$VID" --out "$OUT" --maps "$MAPS" --models-dir "$V/model" >"$V/logs/sa_$ITEM.log" 2>&1
  else
    CUDA_VISIBLE_DEVICES=0 $PY $V/scripts/sa_runner.py --item $ITEM --videos "$VID" --out "$OUT" --models-dir "$V/model" >"$V/logs/sa_$ITEM.log" 2>&1
  fi
  if [ $? -ne 0 ]; then log "$ITEM 예측 실패(로그 logs/sa_$ITEM.log) - 건너뜀"; return; fi
  log "$ITEM 채점(score_sa)"
  { echo "=== $ITEM ($(date +%m-%d)) ==="; $PY $V/scripts/score_sa.py --pred "$OUT" --gt "$VID" --tag "$ITEM 기본규칙"; } > "$V/results/$ITEM.txt" 2>&1
  log "$ITEM 완료 → results/$ITEM.txt"
}

run_item intrusion "$DV/침입(30개)/배포" 1
run_item loiter    "$DV/배회(30개)/배포" 1
run_item fall      "$DV/쓰러짐(10개)/배포" 0
log "QUEUE4(3항목) DONE"

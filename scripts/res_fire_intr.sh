#!/bin/bash
# 방화(6뷰 타일)와 침입(3x3 타일)의 추론 해상도를 바꿔 채점 점수가 어떻게 달라지는지 본다.
# 쓰러짐은 640→960 에서 84.21→90.00 으로 올랐고, 배회는 93.10→79.31 로 떨어졌다.
# 모델 출처(사전학습 vs 우리가 640 으로 파인튜닝)에 따라 방향이 갈리므로 항목마다 재야 한다.
# 끝나면 설정을 원래 값으로 되돌린다(검증 전까지 운영 동작 유지).
# 저장소 루트는 스크립트 위치에서 구한다(경로를 박아 넣지 않는다 · docs/file_path.md 1절).
cd "${VMS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}" || exit 1
PY=.venv/bin/python
KI=_kisa_port/tools/kisa_items.py
M="data/원본데이터/kisa_배포_검증영상/zone_maps"

FD="data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
for z in 640 960; do
  sed -i "s/view_imgsz=[0-9]*/view_imgsz=$z/" "$KI"
  echo "===== 방화 6뷰 imgsz $z"
  $PY "$KI" --item fire --videos "$FD" --gt "$FD" --out "/tmp/fire$z" 2>&1 | grep -E '^\[fire\]'
done
sed -i "s/view_imgsz=[0-9]*/view_imgsz=640/" "$KI"

ID="data/원본데이터/kisa_배포_검증영상/deploy_val/침입(30개)/배포"
for z in 960 1280; do
  sed -i "s/^TILE = dict(grid=3, overlap=0.2, imgsz=[0-9]*/TILE = dict(grid=3, overlap=0.2, imgsz=$z/" "$KI"
  echo "===== 침입 3x3타일 imgsz $z"
  $PY "$KI" --item intrusion --videos "$ID" --gt "$ID" --maps "$M" --out "/tmp/intr$z" 2>&1 | grep -E '^\[intrusion\]'
done
sed -i "s/^TILE = dict(grid=3, overlap=0.2, imgsz=[0-9]*/TILE = dict(grid=3, overlap=0.2, imgsz=960/" "$KI"
echo "설정 원복 완료"

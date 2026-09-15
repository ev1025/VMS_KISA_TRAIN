#!/bin/bash
# 배회 추론 해상도 비교(640 vs 960). 끝나면 설정을 원래 값(640)으로 되돌린다.
# 쓰러짐에서 같은 조건(전체 프레임·타일 없음)을 960 으로 올려 84.21 → 90.00 이 됐으므로 배회도 확인한다.
# 저장소 루트는 스크립트 위치에서 구한다(경로를 박아 넣지 않는다 · docs/file_path.md 1절).
cd "${VMS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}" || exit 1
PY=.venv/bin/python
KI=_kisa_port/tools/kisa_items.py
D="data/원본데이터/kisa_배포_검증영상/deploy_val/배회(30개)/배포"
M="data/원본데이터/kisa_배포_검증영상/zone_maps"

for z in 640 960; do
  sed -i "s/track_imgsz=[0-9]*/track_imgsz=$z/" "$KI"
  echo "===== 배회 imgsz $z"
  $PY "$KI" --item loitering --videos "$D" --gt "$D" --maps "$M" --out "/tmp/loi$z" 2>&1 | tail -20
done
sed -i "s/track_imgsz=[0-9]*/track_imgsz=640/" "$KI"      # 검증 전까지 운영 동작 유지
echo "설정 원복(640) 완료"

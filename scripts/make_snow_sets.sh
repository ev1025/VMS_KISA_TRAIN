#!/bin/bash
# 눈 배경 방화 합성을 방식별로 만든다 (2026-09-23 사용자 지시).
#
# 왜 여러 판인가
#   한 가지 방식만 만들면 그게 맞는지 알 수 없다. 학습에서 견주려고 축을 나눈다.
#     기본    지금 방식 (주간눈 10~26px · 야간눈 12~34px, 주황 불꽃)
#     작은불  폭 0.7배. 채점 편의 실제 불이 14~19px 이라 더 작게
#     흐린색  채도 0.5배. 눈밭에서 색이 덜 튀게
#     흑백불  야간 적외선 편 8편에서 뽑은 흰 불덩이. 못 잡는 272(야간 눈)가 이 모습
cd /NHNHOME/WORKSPACE/26mss002_E3/vms || exit 1
PY=.venv/bin/python
set -x
rm -rf data/학습데이터/_불꽃마스크_20260923

$PY scripts/fire_paste.py --name fire_snowbg_기본_20260923   --n-out 2400 --불종류 컬러
$PY scripts/fire_paste.py --name fire_snowbg_작은불_20260923 --n-out 2400 --불종류 컬러 --크기 작게
$PY scripts/fire_paste.py --name fire_snowbg_흐린색_20260923 --n-out 2400 --불종류 컬러 --채도 0.5
$PY scripts/fire_paste.py --name fire_snowbg_흑백불_20260923 --n-out 2400 --불종류 흑백
ls data/학습데이터/_불꽃마스크_20260923 | grep -c _흑백 || true
echo 끝

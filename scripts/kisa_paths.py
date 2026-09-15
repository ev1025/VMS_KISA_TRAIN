# -*- coding: utf-8 -*-
"""KISA 배포 검증영상의 배치와 채점 공통 상수. 한 곳에서만 정의한다.

여러 스크립트가 각자 "data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포" 같은 문자열을
따로 들고 있었다. 폴더가 하나 바뀌면 어디가 깨지는지 알 수 없어 여기로 모은다.
표본 간격(stride)도 같이 둔다. 채점기·박스 덤프가 서로 다른 간격을 쓰면 시각이 어긋난다.
"""
import os
from pathlib import Path

# 저장소 루트. 기본은 이 파일 위치에서 유도하고, 다른 곳에 두고 돌릴 때만 VMS_ROOT 로 덮어쓴다.
V = Path(os.environ.get("VMS_ROOT") or Path(__file__).resolve().parents[1])

DEPLOY_ROOT = V / "data/원본데이터/kisa_배포_검증영상"
DEPLOY_VAL = DEPLOY_ROOT / "deploy_val"          # 항목별 하위폴더에 mp4 와 GT xml 이 같이 있다
ZONE_MAPS = DEPLOY_ROOT / "zone_maps"            # 침입·배회 영역파일(.map)

# 항목 → (영상 하위폴더, kisa_items.py 가 쓰는 항목명)
# 폴더 이름의 "(N개)" 는 배포 DB 원본 이름이라 우리가 바꾸지 않는다.
ITEM_DIR = {
    "방화": ("방화(10개)/배포", "fire"),
    "침입": ("침입(30개)/배포", "intrusion"),
    "배회": ("배회(30개)/배포", "loitering"),
    "쓰러짐": ("쓰러짐(10개)/배포", "falldown"),
}

# 사람 검출 모델을 바꾸면 점수가 달라지는 항목. 쓰러짐은 자세 모델을 써서 제외한다.
PERSON_ITEMS = ("침입", "배회")

SAMPLE_STRIDE_S = 0.5      # 채점 표본 간격. 채점기와 박스 덤프가 같아야 시각이 맞는다
DEFAULT_IMGSZ = 640        # 실험이 따로 지정하지 않을 때의 입력 크기


def videos(item):
    """항목의 배포 영상 폴더. GT xml 도 같은 폴더에 있다."""
    return DEPLOY_VAL / ITEM_DIR[item][0]


def kisa_item(item):
    """kisa_items.py 의 --item 값."""
    return ITEM_DIR[item][1]


def find_mp4(stem):
    """클립 이름(C00_195_0001)으로 배포 영상 찾기. 없으면 None."""
    for p in DEPLOY_VAL.rglob(stem + ".mp4"):
        return p
    return None

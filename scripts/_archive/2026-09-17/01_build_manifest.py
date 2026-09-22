# -*- coding: utf-8 -*-
"""
01. 라벨 색인(manifest) 생성.

입력 : 라벨 폴더의 json 파일들   (원본 800GB 압축은 건드리지 않음)
출력 : manifest.csv            라벨 1개 = 1줄인 전체 색인 (이후 02~04가 읽음)

방식 : json 내용은 안 읽고 '파일명·폴더 경로'만 파싱한다.
       클래스/장소/클립/프레임이 모두 경로에 인코딩돼 있어 내용 없이도 색인 가능 -> 빠름.
"""
import sys, os, csv
from pathlib import Path
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")   # 윈도우 콘솔 한글 깨짐 방지
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/data_prep 상위(루트)에서 config import
import config as C                         # 경로·설정은 config.py 한 곳에 모음


def main():
    C.WORK.mkdir(parents=True, exist_ok=True)   # 작업 폴더(work/) 없으면 생성
    # 안전장치: 출력 폴더가 원본 데이터 안이면 중단 (원본 보호)
    assert C.WORK != C.DATA_ROOT and C.WORK not in C.DATA_ROOT.parents, "출력은 원본 밖이어야 함"

    # 통계 누적기: 클래스별 개수 / 장소별 개수 / 고유 클립 집합 / 총 라벨 수
    by_cls, by_place, clips, n = Counter(), Counter(), set(), 0

    with open(C.MANIFEST_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # CSV 헤더 (이후 02~04 가 이 컬럼명으로 읽음)
        w.writerow(["cls_kr", "cls_code", "place_kr", "clip", "frame", "stem", "json_path", "img_rel"])

        # 라벨 폴더 전체를 재귀 순회하며 .json 만 처리
        for root, _, files in os.walk(C.LABEL_ROOT):
            for fn in files:
                if not fn.endswith(".json"):     # json 아니면 건너뜀
                    continue

                # 폴더 구조: .../{클래스}/{장소}/{클립}/JSON/{파일}.json
                # 경로 뒤에서 4·3·2번째 조각 = 클래스 / 장소 / 클립
                cls_kr, place_kr, clip = Path(root).parts[-4:-1]

                stem = fn[:-5]                   # 파일명에서 ".json" 제거 (예: 0087_FL_FWW_00001)
                last = stem.rsplit("_", 1)[-1]   # 마지막 '_' 뒤 = 프레임 번호 문자열
                frame = int(last) if last.isdigit() else -1   # 숫자면 프레임번호, 아니면 -1

                # 03(선택추출)용: 압축파일 내부의 jpg 상대경로 (클래스 폴더 기준)
                img_rel = f"{cls_kr}\\{place_kr}\\{clip}\\JPG\\{stem}.jpg"

                # 한 줄 기록. cls_code = 한글클래스 -> 약어(불꽃->fl) 매핑
                w.writerow([cls_kr, C.CLS_DIRS.get(cls_kr, "?"), place_kr, clip, frame,
                            stem, os.path.join(root, fn), img_rel])

                # 통계 누적
                n += 1
                by_cls[cls_kr] += 1
                by_place[place_kr] += 1
                clips.add((cls_kr, clip))
                if n % 100000 == 0:              # 10만 개마다 진행상황 출력
                    print(f"  ...{n:,} 처리", flush=True)

    # 완료 요약: 총 라벨/클립 수 + 클래스별·장소별 분포
    print(f"\n[완료] {C.MANIFEST_CSV} | 총 {n:,} / 클립 {len(clips):,}")
    for k, v in by_cls.most_common():
        print(f"  {k:6s}{v:>10,}")              # 클래스별 개수
    for k, v in by_place.most_common():
        print(f"  {k:24s}{v:>10,}")             # 장소별 개수


if __name__ == "__main__":
    main()

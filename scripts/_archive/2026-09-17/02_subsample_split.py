# -*- coding: utf-8 -*-
"""
02. 서브 샘플링 조건 설정 및 train/val 분할 조건 설정

입력
- manifest.csv     : 각 프레임별 정보값   
출력
- extract_list.txt : 압축파일에서 서브샘플링할 이미지 목록
- selected.csv     : train, val이 분할된 이미지, 라벨 목록
- data.yaml        : YOLO 학습 설정 값

처리 :
  1) 하나의 클립(영상)은 12초(360프레임)으로 구성되어 있음 (같은 초의 프레임은 거의 중복값)
    -> FRAMES_PER_CLIP(사용할 프레임 개수)에 맞춰 균등 간격으로 프레임 서브 샘플링
  2) 정상(none) 데이터는 전체의 NORMAL_RATIO(정상 데이터 비율)만 네거티브로 포함
  3) train/val 을 '클립(영상)' 단위로 분할
    -> 프레임 단위로 나누면 같은 장면이 양쪽에 들어가 데이터 누수
    -> 클래스(불꽃/연기/정상) · 장소 층화(8개의 장소) -> 정렬(sorted) -> 셔플 (random_seed를 지정하여 재현성 확보)

"""
import sys, csv, random
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/data_prep 상위(루트)에서 config import
import config as C

# selected.csv 컬럼(헤더와 행 작성에 재사용)
COLS = ["cls_kr", "cls_code", "place_kr", "clip", "frame", "stem", "json_path", "img_rel"]


def pick_even(items, k):
    """리스트에서 균등 간격으로 k개 추출 (k개 이하면 그대로)."""
    if len(items) <= k:
        return items
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def main():
    random.seed(C.SEED)   # 분할 재현성 고정

    # 1) manifest 읽어 클립별로 묶기:  (클래스,장소,클립) -> 라벨행 리스트
    clip_rows = defaultdict(list)
    with open(C.MANIFEST_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            clip_rows[(r["cls_kr"], r["place_kr"], r["clip"])].append(r)

    # 2) 클립마다 프레임순 정렬 -> 균등 서브샘플. 정상 / 비정상(불꽃·연기) 분리
    fs_clips, normal_clips = [], []          # 각 원소 = (클립키, 선택된 행들)
    for key, rows in clip_rows.items():
        rows = sorted((r for r in rows if r["frame"].lstrip("-").isdigit()),
                      key=lambda r: int(r["frame"]))
        sel = pick_even(rows, C.FRAMES_PER_CLIP)
        (normal_clips if key[0] == "정상" else fs_clips).append((key, sel))

    # 3) 정상(네거티브) 상한: 전체 대비 NORMAL_RATIO 비율까지만 사용
    n_fs = sum(len(s) for _, s in fs_clips)
    cap = int(C.NORMAL_RATIO / (1 - C.NORMAL_RATIO) * n_fs)
    normal_clips.sort(key=lambda kv: kv[0])   # 정렬 후 셔플 -> manifest 순서와 무관하게 재현
    random.shuffle(normal_clips)
    kept_normal, acc = [], 0
    for item in normal_clips:
        if acc >= cap:
            break
        kept_normal.append(item)
        acc += len(item[1])
    print(f"불꽃+연기 {n_fs:,} / 정상 상한 {cap:,} -> 정상 사용 {acc:,}")

    all_clips = fs_clips + kept_normal
    all_clips.sort(key=lambda kv: kv[0])     # 클립키 정렬 -> 출력 순서까지 manifest 무관하게 고정

    # 4) (클래스,장소)별로 묶어 클립 단위 train/val 분할
    split_of = {}                            # 클립키 -> 'train' / 'val'
    strata = defaultdict(list)
    for key, _ in all_clips:
        strata[(key[0], key[1])].append(key)
    for st in sorted(strata):                # 정렬된 순서로 처리 (재현성)
        keys = sorted(strata[st])            # 키 정렬 후 셔플 -> manifest 순서와 무관
        random.shuffle(keys)
        n_val = max(1, round(len(keys) * C.VAL_RATIO)) if len(keys) > 1 else 0
        for i, key in enumerate(keys):
            split_of[key] = "val" if i < n_val else "train"

    # 5) selected.csv (split 컬럼 추가) + extract_list.txt (추출할 jpg 목록)
    C.WORK.mkdir(parents=True, exist_ok=True)
    extract, counts = set(), defaultdict(int)
    with open(C.SELECTED_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["split"] + COLS)
        for key, sel in all_clips:
            sp = split_of[key]
            for r in sel:
                w.writerow([sp] + [r[c] for c in COLS])
                extract.add(r["img_rel"])
                counts[(sp, r["cls_kr"])] += 1
    C.EXTRACT_LIST.write_text("\n".join(sorted(extract)) + "\n", encoding="utf-8")

    # 6) data.yaml (YOLO 학습 설정 파일)
    ds = str(C.DATASET).replace("\\", "/")
    C.DATA_YAML.write_text(
        f"path: {ds}\ntrain: images/train\nval: images/val\n"
        f"nc: {len(C.CLASS_NAMES)}\nnames: {C.CLASS_NAMES}\n", encoding="utf-8")

    # 요약 출력
    print(f"\n[완료] 선택 {len(extract):,}장")
    for k in sorted(counts):
        print(f"  {k[0]:5s} {k[1]:6s} {counts[k]:>8,}")
    print(f"출력 -> {C.WORK} (selected.csv / extract_list.txt / data.yaml)")


if __name__ == "__main__":
    main()

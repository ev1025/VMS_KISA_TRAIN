# -*- coding: utf-8 -*-
"""데이터 확인 탭용 메타. 학습 데이터셋들(24k·FASDD·손라벨·설경·person)의 이미지·라벨 목록을 모은다.

영상 검수(KISA 배포)와 별개다. 여기는 '학습에 쓴 데이터가 어떻게 생겼나'를 이미지+박스로 둘러보는 용도.
이미지가 수만 장이라 메타에는 파일 경로만 담고(내용 아님), 실제 이미지는 서버가 요청 시 스트리밍한다.
라벨(YOLO txt)도 클라이언트가 필요할 때 /api/label 로 읽는다.
"""
import json
import os
from pathlib import Path

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")

# 보여줄 데이터셋: 원본·대표만 (파생 실험셋 fire_v2/v3/v4, kfold 등은 제외)
DATASETS = [
    ("aihub71751_24k", "24k 방화 (AI허브 71751)", "data/학습데이터/aihub71751_24k", ["fire", "smoke"]),
    ("fasdd_yolo", "FASDD (오픈, 영어)", "data/학습데이터/fasdd_yolo", ["fire", "smoke"]),
    # 설경·설경안개는 같은 성격(FASDD 눈/안개 장면)이라 한 세트로 합쳐 보여준다
    ("fasdd_snowfog", "설경·안개 (FASDD)",
     ["data/학습데이터/fasdd_snowfog", "data/학습데이터/fasdd_snow2"], ["fire", "smoke"]),
    ("human_fire", "방화 손라벨", "data/학습데이터/human_fire", ["fire", "smoke"]),
    ("human_synth", "손라벨 합성", "data/학습데이터/human_synth", ["fire", "smoke"]),
    ("person_v3", "사람 검출 (person_v3)", "data/학습데이터/person_v3", ["person"]),
    ("aihub_int_pl", "AI허브 침입 의사라벨", "data/학습데이터/aihub_int_pl", ["person"]),
]
SAMPLE = 600   # 데이터셋당 목록에 담을 최대 이미지 수 (그 이상은 페이지네이션 대신 샘플)


def scan(rels):
    """images/train 파일 목록을 (샘플링해서) 돌려준다. 라벨 유무·어느 폴더 것인지 함께.
    rels 에 폴더를 여러 개 주면 한 세트로 합친다(같은 파일 이름은 앞쪽 폴더 것을 쓴다)."""
    if isinstance(rels, str):
        rels = [rels]
    found, total = [], 0
    for rel in rels:
        di = G / rel / "images" / "train"
        if not di.is_dir():
            di = G / rel / "images"                     # train 하위 폴더 없이 images/ 에 바로 있는 세트
        if not di.is_dir():
            continue
        names = sorted(os.listdir(di))
        total += len(names)
        found.append((rel, names))
    if not found:
        return [], 0
    seen, merged = set(), []
    for rel, names in found:
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            merged.append((rel, n))
    merged.sort(key=lambda x: x[1])
    # 고르게 샘플 (앞뒤 치우침 방지)
    if len(merged) > SAMPLE:
        step = len(merged) / SAMPLE
        merged = [merged[int(i * step)] for i in range(SAMPLE)]
    out = []
    for rel, n in merged:
        stem = Path(n).stem
        has_label = (G / rel / "labels" / "train" / (stem + ".txt")).exists() or (G / rel / "labels" / (stem + ".txt")).exists()
        out.append({"file": n, "stem": stem, "labeled": has_label, "rel": rel})
    return out, total


def main():
    data = {"datasets": []}
    for key, title, rel, classes in DATASETS:
        rels = rel if isinstance(rel, list) else [rel]
        imgs, total = scan(rels)
        if not imgs:
            print(f"  {title}: 없음, 건너뜀")
            continue
        # 라벨 있는 비율 (샘플 기준)
        nlab = sum(1 for x in imgs if x["labeled"])
        data["datasets"].append({
            "key": key, "title": title, "rel": rels[0], "classes": classes,
            "total": total, "shown": len(imgs), "labeled_ratio": round(nlab / len(imgs), 2),
            "images": imgs,
        })
        print(f"  {title}: 전체 {total} · 표시 {len(imgs)} · 라벨 {nlab}")
    out = G / "dash_v2/dataset_meta.json"
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"저장 {out} ({out.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()

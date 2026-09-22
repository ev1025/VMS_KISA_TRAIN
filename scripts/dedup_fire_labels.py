# -*- coding: utf-8 -*-
"""같은 불에 두 번 쳐진 박스를 하나로 줄인다.

왜 있나 (2026-09-22)
    손라벨 편집기에서 같은 불꽃에 박스를 두 번 그린 프레임이 있다. 서버·토르 양쪽에 다 있어
    합치면서 생긴 것이 아니라 라벨 자체의 중복이다. 35쌍 중 22쌍이 넓이 1.1배 이내로
    사실상 같은 박스다(중앙값 1.06배, 최대 1.48배).

무엇을 중복으로 보나
    같은 프레임(file) · 같은 클래스(cls) · IoU >= 0.5

무엇을 남기나
    넓이가 큰 쪽. 불꽃을 덜 잘라 먹는 쪽이 안전하다. 둘이 거의 같아 어느 쪽을 남겨도
    차이는 미미하지만, 규칙을 고정해 두어야 다시 돌려도 같은 결과가 나온다.

사용
    python dedup_fire_labels.py <fire_labels.json> [--write]
    --write 없으면 무엇이 빠지는지만 보여 준다. 쓸 때는 옆에 .dedup_before 사본을 남긴다.
"""
import argparse
import collections
import itertools
import json
import shutil
from pathlib import Path

IOU_SAME = 0.5


def rect(r):
    return (r["x"] - r["w"] / 2, r["y"] - r["h"] / 2, r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def dedup(rows):
    """(남길 행, 뺄 행). 한 프레임 안에서 겹치는 것끼리 묶어 넓이가 가장 큰 하나만 남긴다."""
    groups = collections.defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r.get("file"), r.get("cls"))].append(i)
    drop = set()
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        # 겹치는 것끼리 한 덩어리로 (박스 셋 이상이 사슬로 겹칠 수 있다)
        parent = {i: i for i in idxs}

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i, j in itertools.combinations(idxs, 2):
            if iou(rect(rows[i]), rect(rows[j])) >= IOU_SAME:
                parent[find(i)] = find(j)
        for _, members in itertools.groupby(sorted(idxs, key=find), key=find):
            members = list(members)
            if len(members) < 2:
                continue
            keep = max(members, key=lambda i: rows[i]["w"] * rows[i]["h"])
            drop.update(m for m in members if m != keep)
    return [r for i, r in enumerate(rows) if i not in drop], [rows[i] for i in sorted(drop)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    p = Path(a.path)
    rows = json.loads(p.read_text(encoding="utf-8"))
    keep, gone = dedup(rows)
    print("%s: %d행 → %d행 (뺀 것 %d)" % (p.name, len(rows), len(keep), len(gone)))
    by_clip = collections.Counter(r.get("clip") for r in gone)
    for clip, n in by_clip.most_common():
        print("    %-18s %d개" % (clip, n))
    if not a.write:
        print("  (미리보기. 실제로 쓰려면 --write)")
        return
    shutil.copy2(p, p.with_suffix(".json.dedup_before"))
    p.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
    left, _ = dedup(keep)
    assert len(left) == len(keep), "한 번 더 돌렸는데 또 빠진다. 규칙이 잘못됐다"
    print("  썼다. 사본 %s" % p.with_suffix(".json.dedup_before").name)


if __name__ == "__main__":
    main()

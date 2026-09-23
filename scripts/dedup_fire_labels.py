# -*- coding: utf-8 -*-
"""같은 불에 두 번 쳐진 박스를 하나로 줄인다.

왜 있나 (2026-09-22)
    손라벨 편집기에서 같은 불꽃에 박스를 두 번 그린 프레임이 있다. 서버·토르 양쪽에 다 있어
    합치면서 생긴 것이 아니라 라벨 자체의 중복이다. 35쌍 중 22쌍이 넓이 1.1배 이내로
    사실상 같은 박스다(중앙값 1.06배, 최대 1.48배).

무엇을 중복으로 보나
    같은 순간(clip + 초) · 같은 클래스(cls) · 겹침
    불은 조금이라도 겹치면 중복이다. 연기만 IoU·파묻힘 기준을 쓴다.

    2026-09-23 에 두 군데를 고쳤다. 사용자가 C058205_002 206초에 박스가 다섯 개 보인다고 지적했다.
    (1) 파일 이름으로 묶고 있었다. 같은 206초가 옛 이름 C058205_002_b.png 와
        새 이름 C058205_002_0206.png 두 개로 저장돼 있어 서로 다른 프레임으로 보고
        비교조차 안 했다. 그런 순간이 41곳이다. 이제 clip 과 초로 묶는다.
    (2) IoU 0.5 만 봤다. 큰 박스 안에 작은 박스가 들어앉으면 IoU 가 낮아 안 잡힌다
        (그 프레임은 141x158 안에 66x83 이 들어앉아 IoU 0.25). 이제 '작은 쪽이 70% 이상
        파묻혔는가' 도 같이 본다. 그런 쌍이 10개 더 있다.
        따로 떨어진 두 불은 파묻히지 않으므로 이 규칙에 안 걸린다.

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
import re
import shutil
from pathlib import Path

# 지금 편집기가 쓰는 파일 이름. dash_v2/js/editor.js 1181줄:
#   file: <클립>_<초 4자리>.png   (예: C058205_002_0206.png)
# _a.png · _b.png · _c.png 는 옛 이름이다. 같은 순간이 두 이름으로 남아 있으면 새 이름이 맞다.
현재이름 = re.compile(r"_\d{4}\.png$")

IOU_SAME = 0.5
COVER_SAME = 0.7        # 작은 쪽이 이만큼 파묻히면 같은 불로 본다


def rect(r):
    return (r["x"] - r["w"] / 2, r["y"] - r["h"] / 2, r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def inter(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def 겹치나(a, b, cls=None):
    """같은 불에 두 번 친 박스인가.

    불(cls 0)은 조금이라도 겹치면 잘못된 것이다(2026-09-23 사용자 확인).
        "fire끼리 겹치면 그냥 잘못된거야. fire는 겹칠 수 없거든"
        불은 한 덩어리로 타므로 두 박스가 겹치면 같은 불에 두 번 친 것이다.
        나란히 난 두 불은 서로 떨어져 있어 박스가 안 겹친다.
    연기(cls 1)는 기둥이 퍼지며 서로 물릴 수 있으므로 예전 기준(IoU 또는 파묻힘)을 쓴다."""
    it = inter(a, b)
    if it <= 0:
        return False
    if cls == 0:
        return True
    if it / (area(a) + area(b) - it) >= IOU_SAME:
        return True
    작은쪽 = min(area(a), area(b))
    return 작은쪽 > 0 and it / 작은쪽 >= COVER_SAME


def 순간(r):
    """묶는 열쇠. 파일 이름이 아니라 '어느 클립의 몇 초' 로 묶는다.
    같은 순간이 옛 이름과 새 이름 두 개로 저장된 곳이 41군데 있다."""
    if r.get('clip') is not None and r.get('t') is not None:
        return (r['clip'], round(float(r['t'])))
    return (r.get('file'),)


def dedup(rows, prefer=None):
    """(남길 행, 뺄 행). 한 프레임 안에서 겹치는 것끼리 묶어 하나만 남긴다.

    prefer 는 '이쪽을 우선한다' 는 행 번호 집합. 합칠 때 들어온 쪽(라벨 작업대)을 넣는다.
    사용자 지시(2026-09-22): "겹치는 박스가 있으면 무조건 토르 우선".
    작업대에서 방금 다시 그린 것이 서버에 남은 옛 박스보다 정확하기 때문이다.
    prefer 가 없거나 한 덩어리에 prefer 가 없으면 넓이가 큰 것을 남긴다(불꽃을 덜 잘라 먹는 쪽).
    """
    groups = collections.defaultdict(list)
    for i, r in enumerate(rows):
        groups[순간(r) + (r.get("cls"),)].append(i)
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
            if 겹치나(rect(rows[i]), rect(rows[j]), rows[i].get("cls")):
                parent[find(i)] = find(j)
        for _, members in itertools.groupby(sorted(idxs, key=find), key=find):
            members = list(members)
            if len(members) < 2:
                continue
            # 1순위: 들어온 쪽(작업대). 2순위: 지금 편집기 이름으로 저장된 것.
            # 3순위: 넓이가 큰 것.
            pref = [i for i in members if prefer and i in prefer]
            pool = pref or members                 # 우선할 것이 있으면 그 안에서만 고른다
            새것 = [i for i in pool if 현재이름.search(rows[i].get("file") or "")]
            if 새것 and len(새것) < len(pool):
                # 옛 이름으로 남은 박스는 다시 그리기 전의 것이다. 실제로 C058205_002 206초에서
                # 옛 박스가 141x158 로 어두운 배경까지 물고 있었고 새 박스 66x83 이 불에 맞았다.
                pool = 새것
            keep = max(pool, key=lambda i: rows[i]["w"] * rows[i]["h"])
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


def selfcheck():
    """겹칠 때 무엇을 남기는지. 규칙이 뒤집히면 라벨이 조용히 옛것으로 되돌아간다."""
    a = {"file": "x.png", "cls": 0, "x": .5, "y": .5, "w": .10, "h": .10}   # 서버에 있던 것
    b = {"file": "x.png", "cls": 0, "x": .5, "y": .5, "w": .08, "h": .08}   # 작업대에서 다시 그린 것
    c = {"file": "x.png", "cls": 1, "x": .5, "y": .5, "w": .10, "h": .10}   # 클래스가 다르면 남남
    keep, _ = dedup([a, b])
    assert len(keep) == 1 and keep[0]["w"] == .10, "우선순위가 없으면 큰 쪽"
    keep, _ = dedup([a, b], prefer={1})
    assert len(keep) == 1 and keep[0]["w"] == .08, "들어온 쪽은 작아도 이긴다"
    keep, _ = dedup([a, b], prefer={99})
    assert keep[0]["w"] == .10, "그 덩어리에 우선할 것이 없으면 큰 쪽"
    assert len(dedup([a, c])[0]) == 2, "클래스가 다르면 겹쳐도 그대로 둔다"
    assert len(dedup([a])[0]) == 1, "하나뿐이면 그대로"

    # 2026-09-23 에 고친 두 가지
    큰 = {"file": "C_b.png", "clip": "C", "t": 206, "cls": 0, "x": .327, "y": .582, "w": .110, "h": .219}
    작은 = {"file": "C_0206.png", "clip": "C", "t": 206, "cls": 0, "x": .353, "y": .582, "w": .051, "h": .116}
    keep, _ = dedup([큰, 작은])
    assert len(keep) == 1, "파일 이름이 달라도 같은 클립·같은 초면 한 순간이다"
    assert keep[0]["file"] == "C_0206.png", "옛 이름과 새 이름이 겹치면 새 이름이 이긴다(작아도)"
    떨어진 = {"file": "C_0206.png", "clip": "C", "t": 206, "cls": 0, "x": .368, "y": .778, "w": .034, "h": .033}
    keep, _ = dedup([큰, 작은, 떨어진])
    assert len(keep) == 2, "따로 난 두 번째 불은 남겨야 한다"

    # 불은 조금만 겹쳐도 중복 (2026-09-23)
    불1 = {"file": "C_0100.png", "clip": "C", "t": 100, "cls": 0, "x": .30, "y": .50, "w": .10, "h": .10}
    불2 = {"file": "C_0100.png", "clip": "C", "t": 100, "cls": 0, "x": .39, "y": .50, "w": .10, "h": .10}   # 1% 만 물림
    assert len(dedup([불1, 불2])[0]) == 1, "불은 조금이라도 겹치면 하나만 남긴다"
    안겹침 = {"file": "C_0100.png", "clip": "C", "t": 100, "cls": 0, "x": .60, "y": .50, "w": .10, "h": .10}
    assert len(dedup([불1, 안겹침])[0]) == 2, "떨어진 두 불은 둘 다 남긴다"
    연기1 = {"file": "C_0100.png", "clip": "C", "t": 100, "cls": 1, "x": .30, "y": .50, "w": .10, "h": .10}
    연기2 = {"file": "C_0100.png", "clip": "C", "t": 100, "cls": 1, "x": .39, "y": .50, "w": .10, "h": .10}
    assert len(dedup([연기1, 연기2])[0]) == 2, "연기는 조금 물리는 것을 남긴다(기둥이 퍼진다)"
    print("자체 점검 통과 (11건)")


if __name__ == "__main__":
    import sys
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        main()

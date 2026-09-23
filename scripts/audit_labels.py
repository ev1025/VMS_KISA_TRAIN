# -*- coding: utf-8 -*-
"""손라벨 파일의 상태를 센다. 고치지 않는다. (2026-09-23)

보는 것
    겹침        같은 클립·같은 초·같은 클래스 박스가 서로 물리는 쌍
                불은 조금이라도 물리면 잘못이다(사용자 확인). 연기는 기둥이 퍼져 물릴 수 있다.
    이름        한 순간이 파일 이름 둘로 저장돼 있는가. build_trainset 이 file 을 출력 이미지
                이름으로 쓰므로, 둘이면 같은 프레임이 이미지 두 장으로 나가고 라벨이 나뉜다.
    화면 밖     YOLO 좌표는 0~1 안이어야 한다.
    표시 충돌   '객체 없음'(cls=-1) 표시와 박스가 한 순간에 같이 있는가.
    저장 시각   합칠 때 어느 쪽이 새것인지 가르는 값(ts). 없으면 프레임 단위 교체가 안 된다.

사용
    python3 audit_labels.py <labels.json> [이름]
"""
import collections
import itertools
import json
import re
import sys
from pathlib import Path

현재이름 = re.compile(r"_\d{4}\.png$")


def rect(r):
    return (r["x"] - r["w"] / 2, r["y"] - r["h"] / 2, r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)


def inter(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def main():
    p = Path(sys.argv[1])
    이름 = sys.argv[2] if len(sys.argv) > 2 else p.name
    rows = json.loads(p.read_text(encoding="utf-8"))
    cls수 = collections.Counter(r.get("cls") for r in rows)

    겹침 = collections.Counter()
    g = collections.defaultdict(list)
    for r in rows:
        if int(r.get("cls", -1)) >= 0 and r.get("t") is not None:
            g[(r.get("clip"), round(float(r["t"])), r["cls"])].append(rect(r))
    for (c, t, cl), v in g.items():
        for a, b in itertools.combinations(v, 2):
            if inter(a, b) > 0:
                겹침[cl] += 1

    이름둘 = collections.defaultdict(set)
    밖 = 0
    표시 = collections.defaultdict(lambda: [0, 0])
    ts있음 = 0
    for r in rows:
        if r.get("ts") is not None:
            ts있음 += 1
        if r.get("t") is None:
            continue
        k = (r.get("clip"), round(float(r["t"])))
        이름둘[k].add(r.get("file"))
        if int(r.get("cls", -1)) >= 0:
            표시[k][0] += 1
            a = rect(r)
            if a[0] < -0.002 or a[1] < -0.002 or a[2] > 1.002 or a[3] > 1.002:
                밖 += 1
        else:
            표시[k][1] += 1

    # 사람은 앞뒤로 서서 서로 가린다. 겹치는 것이 정상이다.
    # 불은 한 덩어리로 타므로 겹치면 같은 불에 두 번 친 것이다.
    사람 = "person" in p.name.lower() or "사람" in 이름

    나쁨 = []
    print("=== %s : %d행 (%s %d · 연기 %d · 객체없음표시 %d) ===" % (
        이름, len(rows), "사람" if 사람 else "불",
        cls수.get(0, 0), cls수.get(1, 0), cls수.get(-1, 0)))
    for 항목, 값, 기준 in (
        ("클래스0 끼리 겹침" + ("(사람은 정상)" if 사람 else ""),
         겹침.get(0, 0), None if 사람 else 0),
        ("클래스1(연기) 끼리 겹침", 겹침.get(1, 0), None),
        ("한 순간에 파일 이름 둘 이상", sum(1 for v in 이름둘.values() if len(v) > 1), 0),
        ("화면 밖으로 나간 박스", 밖, 0),
        ("박스와 '없음' 표시 공존", sum(1 for a, b in 표시.values() if a and b), 0),
    ):
        표 = "OK" if 기준 is None or 값 == 기준 else "고쳐야 함"
        if 기준 is not None and 값 != 기준:
            나쁨.append(항목)
        print("  %-28s %6d   %s" % (항목, 값, 표))
    print("  %-28s %6d/%d  %s" % ("저장 시각(ts) 있는 행", ts있음, len(rows),
                                  "OK" if ts있음 == len(rows) else "앞으로 저장하는 것부터 붙는다"))
    return 1 if 나쁨 else 0


if __name__ == "__main__":
    sys.exit(main())

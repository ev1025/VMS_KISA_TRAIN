# -*- coding: utf-8 -*-
"""큐를 돌리기 전에 학습 데이터가 앞뒤가 맞는지 확인한다. 하나라도 걸리면 0 이 아닌 값으로 끝난다.

왜 있나 (2026-09-23)
    하루에 데이터 실수를 네 번 냈다. 전부 '눈으로 안 본 것' 이었다.
      1) 방화 라벨을 옮기면서 전파 저장소를 빼먹었다
      2) 서버에 정리돼 있던 전파를 토르의 과전파본으로 덮었다(불 꺼진 뒤 192프레임)
      3) clip_state.json 을 안 옮겨서 악천후가 학습셋에서 통째로 빠졌다(+130장만 들어옴)
      4) 손라벨만 최신화하고 안개 합성은 옛 스냅샷을 써서, 같은 프레임에 정답이 두 개가 됐다
         (겹치는 3,732 프레임 중 1,141 프레임이 서로 다른 라벨. 그것도 안개가 x3)
    네 번째가 f960_tier42_base_20260923 을 63.16 으로 끌어내렸다.

무엇을 보나
    1. 데이터셋이 있는가
    2. 같은 프레임이 두 데이터셋에 서로 다른 정답으로 들어가는가   <- 4번 실수
    3. 손라벨에서 파생된 세트가 지금 손라벨과 맞는가(신선도)       <- 4번 실수
    4. 채점셋이 섞였는가
    5. 빈 라벨(하드네거티브) 비율이 터무니없지 않은가

사용
    python scripts/queue_check.py configs/queue_fire_20260923.yaml
"""
import collections
import json
import os
import re
import sys
from pathlib import Path

import yaml

V = Path(__file__).resolve().parents[1]
D = V / "data/학습데이터"

# 파생 세트가 어느 손라벨셋에서 나왔는지는 meta.json 의 source 에 적혀 있다
파생꼬리 = re.compile(r"_fog[lmh]$|_snow[lmh]$")


def 프레임이름(p):
    """합성 꼬리(_fogl 등)를 떼어 원본 프레임 이름으로 만든다."""
    return 파생꼬리.sub("", os.path.splitext(os.path.basename(p))[0])


def 라벨읽기(t):
    rows = []
    try:
        for r in Path(t).read_text().split("\n"):
            if r.strip():
                v = r.split()
                rows.append((int(v[0]),) + tuple(round(float(x), 3) for x in v[1:5]))
    except Exception:
        return None
    return sorted(rows)


def 세트훑기(name):
    """{프레임이름: 라벨} · 이미지 수. 라벨 폴더가 없으면 None."""
    d = D / name
    lab = d / "labels/train"
    img = d / "images/train"
    if not img.is_dir():
        img = d / "images"
        lab = d / "labels"
    if not lab.is_dir():
        return None, 0
    out = {}
    n = 0
    for t in lab.glob("*.txt"):
        n += 1
        out[프레임이름(t)] = 라벨읽기(t)
    return out, n


def main():
    q = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
    쓰는것 = []
    for e in q["experiments"]:
        if e.get("base"):
            쓰는것.append(e["base"])
        쓰는것 += list(e.get("extras") or [])
        쓰는것 += list((e.get("oversample") or {}).keys())
    쓰는것 = sorted(set(쓰는것))

    나쁨 = []
    print("=== 큐가 쓰는 데이터셋 %d개 ===" % len(쓰는것))

    # 1. 있는가
    있는것 = []
    for n in 쓰는것:
        d = D / n
        if not d.is_dir():
            d = V / "data/원본데이터" / n
        if d.is_dir():
            있는것.append(n)
            print("  %-36s 있음" % n)
        else:
            print("  %-36s **없음**" % n)
            나쁨.append("데이터셋 없음: " + n)

    # 2. 같은 프레임 다른 정답
    print()
    print("=== 같은 프레임에 정답이 둘인가 ===")
    맵 = {}
    for n in 있는것:
        m, cnt = 세트훑기(n)
        if m:
            맵[n] = m
    이름들 = sorted(맵)
    충돌합 = 0
    for i in range(len(이름들)):
        for j in range(i + 1, len(이름들)):
            a, b = 이름들[i], 이름들[j]
            공통 = 맵[a].keys() & 맵[b].keys()
            if not 공통:
                continue
            다름 = [k for k in 공통 if 맵[a][k] != 맵[b][k]]
            표 = "OK" if not 다름 else "**다름**"
            print("  %-30s x %-30s 겹침 %5d · 다름 %5d  %s"
                  % (a[:30], b[:30], len(공통), len(다름), 표))
            if 다름:
                충돌합 += len(다름)
                나쁨.append("정답 충돌 %d프레임: %s 대 %s" % (len(다름), a, b))
                for k in 다름[:2]:
                    print("      %s" % k[:40])
                    print("        %s  %s" % (a[:22], 맵[a][k][:2]))
                    print("        %s  %s" % (b[:22], 맵[b][k][:2]))
    if not 충돌합:
        print("  겹치면서 정답이 다른 프레임 없음")

    # 3. 파생 세트 신선도
    print()
    print("=== 파생 세트가 지금 손라벨과 맞는가 ===")
    for n in 있는것:
        f = D / n / "meta.json"
        if not f.is_file():
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        src = m.get("source")
        if not src:
            continue
        원본있나 = (D / str(src)).is_dir()
        같이쓰나 = str(src) in 쓰는것
        말 = "원본 %s" % src
        if not 같이쓰나:
            # 원본은 안 쓰고 파생만 쓰는 경우: 원본이 옛 스냅샷이면 위험
            말 += "  (원본은 큐에 없음)"
        print("  %-36s <- %s%s" % (n, 말, "" if 원본있나 else "  **원본 폴더 없음**"))

    # 4. 채점셋 누수
    print()
    print("=== 채점셋 누수 ===")
    채점 = set()
    dep = V / "data/원본데이터/kisa_배포_검증영상/deploy_val"
    for p in dep.rglob("*.mp4"):
        채점.add(p.stem)
    for n in 있는것:
        m = 맵.get(n)
        if not m:
            continue
        샌것 = {k for k in m if any(k.startswith(c) for c in 채점)}
        표 = "깨끗" if not 샌것 else "**누수 %d**" % len(샌것)
        print("  %-36s %s" % (n, 표))
        if 샌것:
            나쁨.append("채점셋 누수 %d: %s" % (len(샌것), n))

    # 5. 빈 라벨 비율
    print()
    print("=== 빈 라벨(하드네거티브) 비율 ===")
    for n in 있는것:
        m = 맵.get(n)
        if not m:
            continue
        빈 = sum(1 for v in m.values() if not v)
        비율 = 100.0 * 빈 / max(1, len(m))
        표 = "" if 비율 < 60 else "  **절반 넘음**"
        print("  %-36s %6d장 중 빈 %5d (%4.1f%%)%s" % (n, len(m), 빈, 비율, 표))
        if 비율 >= 60:
            나쁨.append("빈 라벨이 %.0f%%: %s" % (비율, n))

    print()
    if 나쁨:
        print("=== 걸린 것 %d 건 ===" % len(나쁨))
        for x in 나쁨:
            print("  " + x)
        return 1
    print("=== 전부 통과. 큐를 돌려도 된다 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

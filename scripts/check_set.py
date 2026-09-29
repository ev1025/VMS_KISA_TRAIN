# -*- coding: utf-8 -*-
"""다 지어진 학습셋 폴더 하나가 성한지 본다. 하나라도 걸리면 0 이 아닌 값으로 끝난다.

queue_check.py 와 다른 것
    queue_check 는 '큐에 걸린 여러 세트가 서로 앞뒤가 맞나' 를 본다(같은 프레임 두 답·신선도).
    이 파일은 '세트 하나가 그 자체로 성한가' 를 본다(짝·형식·겹침·깨짐).
    둘 다 돌려야 한다.

무엇을 보나
    1. 이미지와 라벨이 짝이 맞나
    2. 라벨 형식이 성한가(필드 5개·클래스 범위·좌표 0~1·폭높이 양수)
    3. train 과 val 에 같은 프레임이 양다리로 들어갔나
    4. 한 순간이 두 이름으로 들어갔나(_a/_b 같은 옛 이름이 새 이름과 겹치는 것)
    5. 채점 전용 클립이 섞였나
    6. 빈 라벨(하드네거티브) 비율이 터무니없지 않나
    7. data.yaml·train.txt·val.txt 가 실제 파일과 맞나
    8. meta.json 에 적힌 장수가 실제와 맞나
    9. 이미지가 열리나(표본)
   10. (사람 세트) 라벨 대상인 악천후 편이 실제로 들어갔나
       대상 = clip_state 에 완료 표시가 찍힌 편. 표시 없는 편은 일부러 안 한 것이라 세지 않는다

사용
    python scripts/check_set.py trainset_person_20260924
    python scripts/check_set.py trainset_person_20260924 --표본 500
    python scripts/check_set.py --자체시험
"""
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

V = Path(__file__).resolve().parents[1]
D = V / "data/학습데이터"
RAW = V / "data/원본데이터"

옛이름꼬리 = re.compile(r"_[abc]$")          # 지난 편집기가 붙이던 꼬리. 새 이름과 겹치면 한 순간이 두 장이 된다
합성꼬리 = re.compile(r"_fog[lmh]$|_snow[lmh]$")


def 프레임이름(stem):
    """합성 꼬리를 떼어 원본 프레임 이름으로 만든다."""
    return 합성꼬리.sub("", stem)


def 라벨한줄(줄, 클래스수):
    """한 줄을 뜯어본다. 성하면 (클래스, x, y, w, h), 아니면 탈난 이유 문자열."""
    v = 줄.split()
    if len(v) != 5:
        return "필드가 %d개(5개여야 함)" % len(v)
    try:
        c = int(v[0])
        x, y, w, h = (float(t) for t in v[1:])
    except ValueError:
        return "숫자가 아님"
    if not (0 <= c < 클래스수):
        return "클래스 %d (0~%d 이어야 함)" % (c, 클래스수 - 1)
    for 이름, 값 in (("x", x), ("y", y), ("w", w), ("h", h)):
        if not (-1e-6 <= 값 <= 1 + 1e-6):
            return "%s=%.4f 가 0~1 밖" % (이름, 값)
    if w <= 0 or h <= 0:
        return "폭·높이가 0 이하(w=%.4f h=%.4f)" % (w, h)
    if x - w / 2 < -1e-3 or x + w / 2 > 1 + 1e-3 or y - h / 2 < -1e-3 or y + h / 2 > 1 + 1e-3:
        return "박스가 화면 밖(x=%.3f w=%.3f y=%.3f h=%.3f)" % (x, w, y, h)
    return (c, x, y, w, h)


def 클립목록(카테고리):
    """원본데이터 아래 한 카테고리의 영상 이름들."""
    d = RAW / 카테고리
    return {p.stem for p in d.rglob("*.mp4")} if d.is_dir() else set()


def 완료표시된():
    """clip_state.json 에서 완료(hand) 나 전파(prop) 표시가 찍힌 클립 이름.
    표시가 없는 편은 일부러 안 한 것이다. 학습셋 대상이 아니므로 빠진 것으로 세지 않는다."""
    p = D / "손라벨/clip_state.json"
    if not p.is_file():
        return set()
    표 = json.loads(p.read_text(encoding="utf-8"))
    return {k for k, v in 표.items() if isinstance(v, dict) and v.get("mark") in ("hand", "prop")}


def 채점클립():
    """datasets.yaml 에서 use=eval 인 카테고리의 영상 이름. 학습에 절대 들어가면 안 된다."""
    import yaml
    표 = yaml.safe_load(open(V / "configs/datasets.yaml", encoding="utf-8"))
    나온것 = set()
    for 이름, 설정 in 표.items():
        if isinstance(설정, dict) and 설정.get("use") == "eval":
            나온것 |= 클립목록(이름)
    return 나온것


def 검사(이름, 표본수=300):
    d = D / 이름
    if not d.is_dir():
        print("그런 세트가 없다: %s" % d)
        return ["세트 없음"]

    나쁨 = []
    쪽마다 = {}

    # --- 1. 짝이 맞나
    print("=== 1. 이미지·라벨 짝")
    for 쪽 in ("train", "val"):
        img = {p.stem: p for p in (d / "images" / 쪽).glob("*") if p.is_file()}
        lab = {p.stem: p for p in (d / "labels" / 쪽).glob("*.txt")}
        쪽마다[쪽] = (img, lab)
        라벨없음 = sorted(set(img) - set(lab))
        이미지없음 = sorted(set(lab) - set(img))
        print("  %-6s 이미지 %6d · 라벨 %6d · 라벨없는이미지 %d · 이미지없는라벨 %d"
              % (쪽, len(img), len(lab), len(라벨없음), len(이미지없음)))
        if 라벨없음:
            나쁨.append("%s 라벨없는 이미지 %d장 (%s ...)" % (쪽, len(라벨없음), 라벨없음[0]))
        if 이미지없음:
            나쁨.append("%s 이미지없는 라벨 %d장 (%s ...)" % (쪽, len(이미지없음), 이미지없음[0]))

    # --- 2. 라벨 형식
    print()
    print("=== 2. 라벨 형식")
    클래스수 = 1
    y = d / "data.yaml"
    if y.is_file():
        import yaml
        클래스수 = max(1, len(yaml.safe_load(open(y, encoding="utf-8")).get("names") or [0]))
    탈난것 = []
    빈장 = defaultdict(int)
    상자수 = 0
    for 쪽, (img, lab) in 쪽마다.items():
        for stem, t in lab.items():
            줄들 = [r for r in t.read_text().split("\n") if r.strip()]
            if not 줄들:
                빈장[쪽] += 1
                continue
            for 줄 in 줄들:
                r = 라벨한줄(줄, 클래스수)
                if isinstance(r, str):
                    탈난것.append("%s/%s: %s" % (쪽, stem, r))
                else:
                    상자수 += 1
    print("  클래스 %d개 · 상자 %d개 · 탈난 줄 %d개" % (클래스수, 상자수, len(탈난것)))
    for s in 탈난것[:5]:
        print("    %s" % s)
    if 탈난것:
        나쁨.append("탈난 라벨 줄 %d개" % len(탈난것))

    # --- 3. train·val 양다리
    print()
    print("=== 3. train·val 양다리")
    t쪽 = {프레임이름(s) for s in 쪽마다["train"][1]}
    v쪽 = {프레임이름(s) for s in 쪽마다["val"][1]}
    양다리 = sorted(t쪽 & v쪽)
    print("  겹친 프레임 %d개" % len(양다리))
    if 양다리:
        print("    %s ..." % 양다리[0])
        나쁨.append("train·val 양다리 %d프레임" % len(양다리))

    # --- 4. 한 순간이 두 이름으로
    print()
    print("=== 4. 한 순간 두 이름")
    두이름 = []
    for 쪽, (img, lab) in 쪽마다.items():
        stems = set(lab)
        for s in stems:
            민것 = 옛이름꼬리.sub("", s)
            if 민것 != s and 민것 in stems:
                두이름.append("%s/%s 와 %s" % (쪽, s, 민것))
    print("  겹친 순간 %d개" % len(두이름))
    for s in 두이름[:5]:
        print("    %s" % s)
    if 두이름:
        나쁨.append("한 순간 두 이름 %d개" % len(두이름))

    # --- 5. 채점셋 누수
    print()
    print("=== 5. 채점 전용 클립 누수")
    채점 = 채점클립()
    샌것 = []
    for 쪽, (img, lab) in 쪽마다.items():
        for s in lab:
            if any(s.startswith(c) for c in 채점):
                샌것.append("%s/%s" % (쪽, s))
    print("  채점 클립 %d편 대조 · 샌 것 %d장" % (len(채점), len(샌것)))
    for s in 샌것[:5]:
        print("    %s" % s)
    if 샌것:
        나쁨.append("채점셋 누수 %d장" % len(샌것))

    # --- 6. 빈 라벨 비율
    print()
    print("=== 6. 빈 라벨(하드네거티브) 비율")
    for 쪽, (img, lab) in 쪽마다.items():
        n = max(1, len(lab))
        비율 = 100.0 * 빈장[쪽] / n
        print("  %-6s %6d장 중 빈 %6d (%.1f%%)" % (쪽, len(lab), 빈장[쪽], 비율))
        if 비율 > 60:
            나쁨.append("%s 빈 라벨 %.1f%% (너무 높다)" % (쪽, 비율))

    # --- 7. 목록 파일이 실제와 맞나
    print()
    print("=== 7. data.yaml·train.txt·val.txt")
    for 쪽 in ("train", "val"):
        lst = d / ("%s.txt" % 쪽)
        if not lst.is_file():
            print("  %s.txt 없음(러너가 폴더를 직접 읽으면 정상)" % 쪽)
            continue
        적힌것 = [r.strip() for r in lst.read_text().split("\n") if r.strip()]
        없는것 = [r for r in 적힌것 if not Path(r if os.path.isabs(r) else d / r).is_file()]
        print("  %-6s 목록 %6d줄 · 실제 이미지 %6d장 · 목록에만 있는 것 %d"
              % (쪽, len(적힌것), len(쪽마다[쪽][0]), len(없는것)))
        if 없는것:
            나쁨.append("%s.txt 에 없는 파일 %d줄" % (쪽, len(없는것)))
        if len(적힌것) != len(쪽마다[쪽][0]):
            나쁨.append("%s.txt 줄수(%d)와 실제 이미지수(%d)가 다르다" % (쪽, len(적힌것), len(쪽마다[쪽][0])))

    # --- 8. meta.json 과 맞나
    print()
    print("=== 8. meta.json 대조")
    m = d / "meta.json"
    if m.is_file():
        j = json.loads(m.read_text(encoding="utf-8"))
        for 쪽 in ("train", "val"):
            적힌수 = j.get(쪽)
            실제 = len(쪽마다[쪽][0])
            맞나 = "맞음" if 적힌수 == 실제 else "**다름**"
            print("  %-6s meta %s · 실제 %d  %s" % (쪽, 적힌수, 실제, 맞나))
            if 적힌수 != 실제:
                나쁨.append("meta %s=%s 인데 실제 %d" % (쪽, 적힌수, 실제))
        print("  %s" % (j.get("stats", {}).get("채점클립 검사", "채점클립 검사 줄 없음")))
    else:
        print("  meta.json 없음")
        나쁨.append("meta.json 없음")

    # --- 9. 이미지가 열리나
    print()
    print("=== 9. 이미지 열림(표본 %d장)" % 표본수)
    import cv2
    모두 = [p for 쪽 in ("train", "val") for p in 쪽마다[쪽][0].values()]
    random.seed(0)
    표본 = random.sample(모두, min(표본수, len(모두)))
    깨진것 = [str(p) for p in 표본 if cv2.imread(str(p)) is None]
    print("  깨진 것 %d장" % len(깨진것))
    for s in 깨진것[:5]:
        print("    %s" % s)
    if 깨진것:
        나쁨.append("깨진 이미지 %d장(표본 %d 중)" % (len(깨진것), len(표본)))

    # --- 10. 악천후가 들어갔나
    #     대상은 45편 전부가 아니라 clip_state 에 완료 표시가 찍힌 편이다.
    #     나머지는 일부러 안 한 것이므로 빠진 것으로 세지 않는다(2026-09-24 확인).
    print()
    print("=== 10. 악천후 편 포함")
    악천후 = 클립목록("KISA_악천후_사람")
    if 악천후:
        대상 = 악천후 & 완료표시된()
        든것 = defaultdict(int)
        for 쪽, (img, lab) in 쪽마다.items():
            for s in lab:
                for c in 대상:
                    if s.startswith(c):
                        든것[c] += 1
                        break
        print("  라벨 대상 %d편 중 %d편 · 프레임 %d장" % (len(대상), len(든것), sum(든것.values())))
        빠진것 = sorted(대상 - set(든것))
        if 빠진것:
            print("  ** 대상인데 안 들어간 편 %d: %s" % (len(빠진것), 빠진것[:8]))
            나쁨.append("악천후 대상 %d편이 안 들어갔다" % len(빠진것))
    else:
        print("  원본 폴더 없음(건너뜀)")

    return 나쁨


def 자체시험():
    """라벨 한 줄 해석이 맞는지만 본다. 나머지는 파일이 있어야 볼 수 있다."""
    assert 라벨한줄("0 0.5 0.5 0.2 0.2", 1) == (0, 0.5, 0.5, 0.2, 0.2)
    assert isinstance(라벨한줄("0 0.5 0.5 0.2", 1), str)              # 필드 4개
    assert isinstance(라벨한줄("0 0.5 0.5 0.2 0.2 0.1", 1), str)      # 필드 6개
    assert isinstance(라벨한줄("1 0.5 0.5 0.2 0.2", 1), str)          # 클래스 범위 밖
    assert 라벨한줄("1 0.5 0.5 0.2 0.2", 2)[0] == 1                   # 2클래스면 통과
    assert isinstance(라벨한줄("0 1.5 0.5 0.2 0.2", 1), str)          # x 가 1 넘음
    assert isinstance(라벨한줄("0 0.5 0.5 0 0.2", 1), str)            # 폭 0
    assert isinstance(라벨한줄("0 0.05 0.5 0.2 0.2", 1), str)         # 박스 왼쪽이 화면 밖
    assert isinstance(라벨한줄("영 0.5 0.5 0.2 0.2", 1), str)         # 숫자 아님
    assert 라벨한줄("0 0.5 0.5 1.0 1.0", 1) == (0, 0.5, 0.5, 1.0, 1.0)  # 화면 꽉 찬 박스는 통과
    assert 프레임이름("C001_0010_fogl") == "C001_0010"
    assert 프레임이름("C001_0010") == "C001_0010"
    assert 옛이름꼬리.sub("", "C001_0010_a") == "C001_0010"
    assert 옛이름꼬리.sub("", "C001_0010") == "C001_0010"
    print("자체시험 통과 (13건)")


if __name__ == "__main__":
    if "--자체시험" in sys.argv:
        자체시험()
        sys.exit(0)
    이름 = sys.argv[1]
    표본 = 300
    if "--표본" in sys.argv:
        표본 = int(sys.argv[sys.argv.index("--표본") + 1])
    나쁨 = 검사(이름, 표본)
    print()
    if 나쁨:
        print("=== 걸린 것 %d 건 ===" % len(나쁨))
        for s in 나쁨:
            print("  %s" % s)
        sys.exit(1)
    print("=== 걸린 것 없음 ===")

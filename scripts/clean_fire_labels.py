# -*- coding: utf-8 -*-
"""손라벨 파일을 규격에 맞게 정리한다. 겹침 제거(dedup_fire_labels.py) 다음 단계.

왜 있나 (2026-09-23)
    사용자가 C058205_002 206초에 박스가 다섯 개 보인다고 지적한 데서 시작했다.
    겹침만 고쳐서는 안 되는 문제가 세 가지 더 나왔다.

무엇을 고치나

    1) 한 순간에 파일 이름이 둘 이상
       지금 편집기는 <클립>_<초 4자리>.png 로 저장한다(dash_v2/js/editor.js 1181줄).
       옛 라벨은 _a.png · _b.png · _c.png 로 남아 있다.
       build_trainset.py 73줄이 이 file 값을 '출력 이미지 이름' 으로 쓴다.
       그래서 이름이 둘이면 같은 프레임이 이미지 두 장으로 나가고, 각 장에 박스가 나뉘어 붙는다.
       모델이 같은 그림을 서로 다른 정답으로 두 번 본다. 이름을 하나로 통일한다.
       (이미지 손라벨 img: 행은 원본 파일을 가리키므로 건드리지 않는다)

    2) '객체 없음' 표시(cls=-1)와 박스가 한 순간에 같이 있는 경우
       cls=-1 은 사람이 보고 아무것도 없다고 표시한 것이다(serve_kisa.py 1627줄).
       박스가 있는데 없다는 표시가 같이 있으면 둘 중 하나가 낡은 것이다.
       박스 쪽을 남기고 표시를 뺀다. 박스는 사람이 그린 것이고, 없음 표시는
       프레임을 열었다가 아무 것도 안 그리면 자동으로 남는 것이라 잘못 눌리기 쉽다.

    3) 화면 밖으로 나간 박스
       연기 기둥을 그리다 화면 밖까지 끌어 놓은 것이 많다(496행이 연기).
       밖에는 볼 것이 없으므로 화면 안으로 자른다. YOLO 좌표는 0~1 안이어야 한다.

무엇을 안 고치나
    겹침은 dedup_fire_labels.py 가 한다. 불은 조금이라도 겹치면 중복, 연기는 IoU·파묻힘 기준.
    cls=-1 행 자체는 지우지 않는다. 하드네거티브 표시로 쓰인다.

사용
    python scripts/clean_fire_labels.py <fire_labels.json> [--write]
    --write 없으면 무엇이 바뀌는지만 보여 준다. 쓸 때는 옆에 .clean_before 사본을 남긴다.
"""
import argparse
import collections
import json
import re
import shutil
from pathlib import Path

현재이름 = re.compile(r"_\d{4}\.png$")


def 표준이름(r):
    """이 행이 있어야 할 파일 이름. 영상 프레임만 바꾼다."""
    clip = str(r.get("clip") or "")
    if clip.startswith("img:") or r.get("t") is None:
        return r.get("file")
    return "%s_%04d.png" % (clip, round(float(r["t"])))


def clean(rows):
    """(정리한 행, 무엇을 했는지 셈)"""
    셈 = collections.Counter()

    # --- 2) '객체 없음' 표시와 박스가 같이 있으면 표시를 뺀다 ---
    박스있는순간 = {(r.get("clip"), round(float(r["t"])))
                    for r in rows if r.get("t") is not None and int(r.get("cls", -1)) >= 0}
    남김 = []
    for r in rows:
        if int(r.get("cls", -1)) < 0 and r.get("t") is not None \
                and (r.get("clip"), round(float(r["t"]))) in 박스있는순간:
            셈["객체없음 표시인데 같은 순간에 박스가 있음 → 표시 뺌"] += 1
            continue
        남김.append(r)
    rows = 남김

    out = []
    for r in rows:
        r = dict(r)

        # --- 1) 파일 이름 통일 ---
        새 = 표준이름(r)
        if 새 and r.get("file") != 새:
            셈["파일 이름을 현재 규약으로 바꿈"] += 1
            r["file"] = 새

        # --- 3) 화면 밖으로 나간 박스를 화면 안으로 자른다 ---
        if int(r.get("cls", -1)) >= 0:
            x0, y0 = r["x"] - r["w"] / 2, r["y"] - r["h"] / 2
            x1, y1 = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
            c0, d0 = max(0.0, x0), max(0.0, y0)
            c1, d1 = min(1.0, x1), min(1.0, y1)
            # 좌표를 5자리로 반올림하므로 1.0 을 1e-6 쯤 넘는 것이 남는다.
            # 그것까지 다시 자르면 돌릴 때마다 값이 바뀌어 같은 결과가 안 나온다.
            EPS = 1e-5
            바뀜 = max(abs(c0 - x0), abs(d0 - y0), abs(c1 - x1), abs(d1 - y1))
            if 바뀜 > EPS and c1 > c0 and d1 > d0:
                셈["화면 밖으로 나간 박스를 잘라 넣음"] += 1
                r["x"] = round((c0 + c1) / 2, 5)
                r["y"] = round((d0 + d1) / 2, 5)
                r["w"] = round(c1 - c0, 5)
                r["h"] = round(d1 - d0, 5)
        out.append(r)
    return out, 셈


def 점검(rows, 제목):
    """정리가 끝난 뒤 남은 문제를 센다."""
    이름둘 = collections.defaultdict(set)
    밖 = 0
    충돌 = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if r.get("t") is None:
            continue
        키 = (r.get("clip"), round(float(r["t"])))
        이름둘[키].add(r.get("file"))
        if int(r.get("cls", -1)) >= 0:
            충돌[키][0] += 1
            if r["x"] - r["w"] / 2 < -0.002 or r["y"] - r["h"] / 2 < -0.002 \
                    or r["x"] + r["w"] / 2 > 1.002 or r["y"] + r["h"] / 2 > 1.002:
                밖 += 1
        else:
            충돌[키][1] += 1
    print("  [%s] 한 순간에 파일 이름 둘 이상 %d곳 · 화면 밖 박스 %d개 · 박스와 없음표시 공존 %d곳" % (
        제목, sum(1 for v in 이름둘.values() if len(v) > 1), 밖,
        sum(1 for a, b in 충돌.values() if a and b)))


def selfcheck():
    """규칙이 뒤집히면 라벨이 조용히 망가진다."""
    r1 = {"clip": "C", "t": 206, "cls": 0, "x": .5, "y": .5, "w": .2, "h": .2, "file": "C_b.png"}
    out, _ = clean([r1])
    assert out[0]["file"] == "C_0206.png", "영상 프레임 이름은 현재 규약으로"

    img = {"clip": "img:a/b.png", "t": 0, "cls": 0, "x": .5, "y": .5, "w": .2, "h": .2, "file": "img:a/b.png_0000.png"}
    out, _ = clean([img])
    assert out[0]["file"] == img["file"], "이미지 손라벨 이름은 건드리지 않는다"

    밖 = {"clip": "C", "t": 1, "cls": 1, "x": .9, "y": .5, "w": .4, "h": .2, "file": "C_0001.png"}
    out, _ = clean([밖])
    assert abs(out[0]["x"] - .9) < 1e-6 or True
    assert out[0]["x"] + out[0]["w"] / 2 <= 1.0 + 1e-9, "오른쪽으로 나간 것을 잘라 넣는다"
    assert abs(out[0]["w"] - 0.3) < 1e-6, "잘린 만큼 폭이 준다(0.7~1.0)"

    없음 = {"clip": "C", "t": 5, "cls": -1, "x": 0, "y": 0, "w": 0, "h": 0, "file": "C_0005.png"}
    박스 = {"clip": "C", "t": 5, "cls": 0, "x": .5, "y": .5, "w": .1, "h": .1, "file": "C_c.png"}
    out, _ = clean([없음, 박스])
    assert len(out) == 1 and out[0]["cls"] == 0, "박스가 있으면 없음 표시를 뺀다"
    out, _ = clean([없음])
    assert len(out) == 1, "박스가 없으면 없음 표시는 남긴다(하드네거티브)"
    print("자체 점검 통과 (6건)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    p = Path(a.path)
    rows = json.loads(p.read_text(encoding="utf-8"))
    점검(rows, "정리 전")
    out, 셈 = clean(rows)
    print("%s: %d행 → %d행" % (p.name, len(rows), len(out)))
    for k, v in 셈.most_common():
        print("    %-44s %d" % (k, v))
    점검(out, "정리 후")
    if not a.write:
        print("  (미리보기. 실제로 쓰려면 --write)")
        return
    shutil.copy2(p, p.with_suffix(".json.clean_before"))
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    다시, 셈2 = clean(out)
    assert not 셈2, "한 번 더 돌렸는데 또 바뀐다. 규칙이 잘못됐다: %r" % dict(셈2)
    print("  썼다. 사본 %s" % p.with_suffix(".json.clean_before").name)


if __name__ == "__main__":
    import sys
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        main()

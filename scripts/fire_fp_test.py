# -*- coding: utf-8 -*-
"""불이 없는 영상에 방화 규칙을 걸어 오경보만 센다.

왜 (2026-09-23)
    채점 10편에 540가지 규칙을 스윕해 고른 값(불 conf 0.14, 6프레임 중 3히트)이
    배포 규칙(0.40, 20중 3)보다 73.68 → 94.74 로 높게 나왔다.
    그런데 그 값은 채점 10편에만 맞춘 것이라 그대로 믿을 수 없다.
    임계값을 내리면 재현율은 오르고 정밀도는 떨어진다. 떨어지는 쪽을 따로 재야 한다.

    화재 영상은 연구개발 75편을 전부 손라벨에 썼다. 모델이 안 본 화재 영상이 없다.
    그래서 재현율은 검증할 수 없다. 대신 정밀도는 잴 수 있다.
    KISA_악천후_사람 45편은 사람 항목 영상이라 불이 안 난다.
    방화 모델 학습에 쓴 적도 없다. 여기서 울리면 전부 오경보다.

무엇을 재나
    규칙마다 "45편 중 몇 편에서 울렸나". 0편이 이상적이다.
    눈·비·안개·야간 편을 따로 센다. 채점에서 놓치는 편이 전부 악천후이기 때문이다.

경로
    채점(score_kisa.py) 과 똑같이 타일 6장·stride 0.5·학습 해상도로 뽑는다.
    다르게 뽑으면 그 숫자로 규칙을 정할 수 없다.

쓰는 법
    python scripts/fire_fp_test.py <가중치.pt> --imgsz 960 --tiles --tag <이름>
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V))
import score_kisa as SK                                   # 덤프·규칙을 그대로 빌려 쓴다

WEATHER = V / "data/원본데이터/KISA_악천후_사람/영상"
PERSON = V / "data/원본데이터/kisa_연구개발_사람영상"
TLDIR = V / "dumps/score_tl"

# 왜 사람영상을 쓰나 (2026-09-23, 사용자 제안)
#   방화 모델이 안 본 원본을 기준으로 규칙을 맞추자는 것. 손라벨 meta 를 보면
#   kisa_연구개발_사람영상 8,199행은 "모드다름" 으로 방화셋에서 빠져 있다. 학습에 안 썼다.
#   825편 전부 불이 없으니 울리면 전부 오경보다. 날씨는 주간맑음 686 · 야간맑음 136 · 야간비 3
#   으로 눈·안개가 0편이다. 그래서 악천후 45편과 같이 쓴다(악천후는 그쪽에만 있다).
#   전편을 뜨면 28시간이라 야간을 먼저 채우고 주간으로 마저 채운다(헛울림은 야간에 난다).

# 후보 규칙. (이름, 불 임계, 창, 히트)
RULES = [
    ("배포  불0.40 20중3", 0.40, 20, 3),
    ("후보A 불0.14  6중3", 0.14, 6, 3),
    ("후보B 불0.26  4중2", 0.26, 4, 2),
    ("후보C 불0.14  4중2", 0.14, 4, 2),
    ("후보D 불0.20  6중3", 0.20, 6, 3),
    ("후보E 불0.30  6중3", 0.30, 6, 3),
    ("후보F 불0.14 10중5", 0.14, 10, 5),
    ("후보G 불0.20 10중5", 0.20, 10, 5),
]


def weather_of(xml):
    """xml 한 편의 날씨를 한글 한 덩이로 돌려준다."""
    w = ET.parse(xml).getroot().find(".//Weather")
    g = lambda k: (w.findtext(k) or "").strip()
    tod = {"Day": "주간", "Night": "야간", "Dawn": "새벽", "Dusk": "해질녘"}.get(g("TimeOfDay"), g("TimeOfDay"))
    bad = [n for n, k in (("눈", "Snow"), ("비", "Rain"), ("안개", "Fog")) if g(k) == "Yes"]
    return tod + ("·" + "·".join(bad) if bad else "·맑음")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--stride", type=float, default=0.5)
    ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--tag", default="fp")
    ap.add_argument("--pool", default="악천후", choices=["악천후", "사람", "둘다"])
    ap.add_argument("--max", type=int, default=0, help="0 이면 전부. 야간을 먼저 고른다")
    a = ap.parse_args()

    TLDIR.mkdir(parents=True, exist_ok=True)
    cache = TLDIR / ("fp_" + a.tag + ".json")

    vids = []
    if a.pool in ("악천후", "둘다"):
        vids += sorted(WEATHER.glob("*.mp4"))
    if a.pool in ("사람", "둘다"):
        vids += sorted(PERSON.rglob("*.mp4"))
    if not vids:
        print("영상이 없습니다 (풀 %s)" % a.pool)
        return 1

    wx = {}
    for v in vids:
        x = v.with_suffix(".xml")
        wx[v.stem] = weather_of(x) if x.is_file() else "알수없음"

    if a.max and len(vids) > a.max:
        # 야간·악천후를 먼저 넣는다. 헛울림은 조명·반사가 있는 야간에 난다.
        def 위험도(v):
            w = wx[v.stem]
            return (0 if w.startswith(("야간", "새벽")) else 1, 0 if "맑음" not in w else 1, v.stem)
        vids = sorted(sorted(vids, key=위험도)[:a.max], key=lambda p: p.stem)
        print("표본 %d편 (야간·악천후 우선)" % len(vids))

    # 덤프는 비싸다(편당 수 분). 한 번 뜨면 파일로 남겨 두고 다시 쓴다.
    if cache.is_file():
        per = {k: [(t, {"fire": f, "smoke": s}) for t, f, s in v] for k, v in json.loads(cache.read_text()).items()}
        print("덤프 다시 씀 %s (%d편)" % (cache.name, len(per)), flush=True)
    else:
        from ultralytics import YOLO
        SK.IMGSZ = a.imgsz
        model = YOLO(a.model)
        per = {}
        for i, v in enumerate(vids, 1):
            per[v.stem] = SK.dump(model, v, a.stride, a.tiles)
            print("  덤프 %2d/%d %s" % (i, len(vids), v.stem), flush=True)
        cache.write_text(json.dumps({k: [[t, b["fire"], b["smoke"]] for t, b in rows] for k, rows in per.items()}))

    악천후 = {s for s, w in wx.items() if "맑음" not in w or w.startswith(("야간", "새벽"))}

    print()
    print("=== 불 없는 영상 %d편 오경보 (야간·악천후 %d편) ===" % (len(per), len(악천후)))
    print("%-20s %8s %8s   %s" % ("규칙", "울린편", "악천후중", "울린 편"))
    표 = []
    for name, fth, win, hits in RULES:
        울림 = []
        for stem, rows in sorted(per.items()):
            r3 = [(t, b["fire"], b["smoke"]) for t, b in rows]
            if SK._onset2(r3, fth=fth, sdelta=9.9, win=win, hits=hits, use_smoke=False) is not None:
                울림.append(stem)
        나쁨 = [s for s in 울림 if s in 악천후]
        표.append((name, len(울림), len(나쁨)))
        보기 = ", ".join("%s(%s)" % (s, wx[s]) for s in 울림[:4]) + (" 외 %d" % (len(울림) - 4) if len(울림) > 4 else "")
        print("%-20s %6d편 %6d편   %s" % (name, len(울림), len(나쁨), 보기 or "없음"))

    print()
    print("읽는 법: 이 45편에는 불이 없다. 울린 편은 전부 오경보다.")
    print("채점 10편에서 점수가 올라도 여기서 많이 울리면 시험장에서 그 점수가 안 나온다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""손라벨 사람 모델의 '처음 보는 영상' 잣대. 연구개발 침입 170편·배회 325편에 채점 경로 덤프를 뜨고,
라벨에 안 쓴 편(침입 117·배회 284)으로 규칙·모델을 잰다.

왜 (2026-09-20)
    채점 견본은 침입 30·배회 30편이라 한 편이 3.3점이고, 쓰러짐에서 본 것처럼 소표본에 맞춘 값은 봉우리일 수 있다.
    연구개발 사람영상 XML 에는 구역 다각형(<Intrusion>/<Loitering>)과 정답 시각(<Alarm>)이 있어 같은 채점기로 점수를 낼 수 있다.
    손라벨 스냅샷(person_mask_hn_20260918)에 프레임이 들어간 편(95편)은 '본 편' 으로 따로 센다.
    남는 편도 같은 장면·카메라가 많아 시험 장면보다는 낙관이다. 방향(어느 규칙·모델이 밖에서 나은가)만 가져간다.

덤프는 항목별 채점 경로 도구 그대로(docs/EXPERIMENTS.md 4.14): 침입 = person_redump(타일, contain 2.0), 배회 = server_tdump(BoT-SORT 전체 프레임, conf 0.20).

사용
    python scripts/person_unseen.py maps
        연구개발 XML → data/원본데이터/kisa_연구개발_사람영상/zone_maps/<편>.map (기존 규칙 도구의 zone_of 호환용)
    python scripts/person_unseen.py dump <실험이름> [--imgsz 1280] [--item 침입|배회|둘]
        → dumps/unseen/<실험>_<해상도>/{intrusion,loiter}/<편>.jsonl  (있는 편은 건너뜀)
    python scripts/person_unseen.py score <실험이름>... [--imgsz 1280]
        본 편 / 안 본 편 · 주간 / 야간 별로 지금 규칙과 후보 규칙 점수(정검/미검/오검)
"""
import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_items as K          # noqa: E402
import intr_rule4 as IR         # noqa: E402
import loiter_rule4 as LR       # noqa: E402

PY = V / ".venv/bin/python"
RD = V / "data/원본데이터/kisa_연구개발_사람영상"
DIRS = {"침입": RD / "2. 침입(170개)", "배회": RD / "1. 배회(325개)"}
TAG = {"침입": "Intrusion", "배회": "Loitering"}
SUB = {"침입": "intrusion", "배회": "loiter"}
RD_MAPS = RD / "zone_maps"
SNAP = V / "data/학습데이터/person_mask_hn_20260918"
OUT = V / "dumps/unseen"


def used_clips():
    """손라벨 스냅샷(학습+검증)에 프레임이 들어간 편."""
    used = set()
    for f in ("train.txt", "val.txt"):
        for line in (SNAP / f).read_text(encoding="utf-8").splitlines():
            m = re.search(r"/([A-Za-z0-9]+_\d+)_\d+\.jpg$", line.strip())
            if m:
                used.add(m.group(1))
    return used


def points_of(node):
    if node is None:
        return []
    return [tuple(int(float(v)) for v in p.text.split(",")) for p in node.findall("Point") if p.text]


def clip_info(item):
    """{편: (구역 다각형, 정답 초, 주야)}  구역은 <Intrusion>/<Loitering>, 없으면 <DetectArea>, 그것도 없으면 화면 전체."""
    info = {}
    for x in sorted(DIRS[item].glob("*.xml")):
        root = ET.parse(x).getroot()
        pts = points_of(root.find(".//" + TAG[item]))
        if len(pts) < 3:
            pts = points_of(root.find(".//DetectArea"))
        if len(pts) < 3:
            pts = [(0, 0), (1280, 0), (1280, 720), (0, 720)]
        al = K.read_alarms(x)
        gt = al[0]["start_s"] if al else None
        info[x.stem] = (pts, gt, root.findtext(".//Weather/TimeOfDay") or "?")
    return info


def cmd_maps(_a):
    RD_MAPS.mkdir(exist_ok=True)
    n = 0
    for item in DIRS:
        for x in sorted(DIRS[item].glob("*.xml")):
            root = ET.parse(x).getroot()
            da = ET.Element("DA")
            ET.SubElement(da, "DetectionAreas").text = root.findtext(".//DetectionAreas") or "2"
            for tag in ("DetectArea", TAG[item]):
                src = root.find(".//" + tag)
                dst = ET.SubElement(da, tag)
                for p in points_of(src):
                    ET.SubElement(dst, "Point").text = "%d,%d" % p
            (RD_MAPS / (x.stem + ".map")).write_bytes(ET.tostring(da, encoding="utf-8", xml_declaration=True))
            n += 1
    print(f"{n}편 .map → {RD_MAPS}")


def best_pt(exp):
    meta = V / "results" / exp / "meta.json"
    if meta.is_file():
        pt = json.loads(meta.read_text(encoding="utf-8")).get("best_pt")
        if pt and Path(pt).is_file():
            return Path(pt)
    pt = V / "runs" / exp / "yolo11s/weights/best.pt"
    if pt.is_file():
        return pt
    raise SystemExit(f"가중치를 못 찾음: {exp}")


def cmd_dump(a):
    pt = best_pt(a.exp)
    out = OUT / f"{a.exp}_{a.imgsz}"
    items = ["침입", "배회"] if a.item == "둘" else [a.item]
    for item in items:
        od = out / SUB[item]
        od.mkdir(parents=True, exist_ok=True)
        if item == "침입":
            cmd = [str(PY), str(V / "scripts/person_redump.py"), str(pt), "--item", "침입", "--videos", str(DIRS[item]),
                   "--out", str(od), "--imgsz", str(a.imgsz), "--contain", "2.0", "--stride", "0.5"]
        else:
            cmd = [str(PY), str(V / "scripts/server_tdump.py"), "--model", str(pt), "--videos", str(DIRS[item]),
                   "--out", str(od), "--stride", "0.5", "--conf", "0.20", "--imgsz", str(a.imgsz)]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=str(V), check=False)
    print("덤프 끝", out, flush=True)


def kisa(gt, sa, clips, desc):
    pairs = [([{"start_s": gt[c], "desc": desc}] if gt.get(c) is not None else [],
              [{"start_s": sa[c], "desc": desc}] if sa.get(c) is not None else []) for c in clips]
    r = K.score(pairs)
    return r.get("점수", 0.0), r.get("정상검출", "?"), r.get("미검출", "?"), r.get("오검출", "?")


RULES = {
    "침입": [
        ("지금 규칙(0.45·꼭짓점3·연속2·gap2)", lambda rows, poly: IR.sa_now(rows, poly)),
        ("합의 규칙(0.35·시작5초무시·유지0.15)", lambda rows, poly: IR.sa_entry(rows, poly, 0.35, 3, 2, 2, 5, 0, lo=0.15)),
    ],
    "배회": [
        ("지금 규칙(0.40·체류6·끊김6·대기5)", lambda rows, poly: LR.sa_now(rows, poly)),
        ("후보(끊김10·발끝10px)", lambda rows, poly: LR.sa_entry(rows, poly, 0.40, 6.0, 0, gap=10, margin=10)),
        ("합의(0.35·끊김10·발끝40px)", lambda rows, poly: LR.sa_entry(rows, poly, 0.35, 6.0, 0, gap=10, margin=40)),
        # 늦게 온 일행 받기(crowd)를 끄면 어떻게 되나. crowd=0 이면 그 예외가 동작하지 않는다.
        ("지금 규칙 - 일행예외 끔", lambda rows, poly: LR.sa_entry(rows, poly, 0.40, 6.0, 0, gap=10, margin=10, crowd=0)),
        # 안내서 표 3-1 은 "10초 이상 배회" 다. 지금은 6초만 머물러도 배회자로 본다.
        ("체류 10초(안내서 정의)", lambda rows, poly: LR.sa_entry(rows, poly, 0.40, 10.0, 0, gap=10, margin=10)),
        ("체류 8초", lambda rows, poly: LR.sa_entry(rows, poly, 0.40, 8.0, 0, gap=10, margin=10)),
    ],
}


def cause(rows, poly, gt, sa, conf_th, item):
    """실패 편의 원인 한 줄. 정답 창 [gt-2, gt+10] 안 구역 안 상자를 본다."""
    if sa is not None:
        return "오검-조기(%+.0f초)" % (sa - gt) if sa < gt - 2 else "오검-지연(%+.0f초)" % (sa - gt)
    confs = []
    for r in rows:
        if gt - 2 <= r["t"] <= gt + 10:
            for b in r["boxes"]:
                pid, conf, x1, y1, x2, y2 = b[:6]
                if K.entered((x1, y1, x2, y2), poly, 3 if item == "침입" else 0):
                    confs.append(conf)
    if not confs:
        return "미검-창안 구역안 검출 없음"
    if max(confs) < conf_th:
        return "미검-약한검출(최대 %.2f)" % max(confs)
    return "미검-체류부족(문턱 이상 표본 %d)" % sum(1 for c in confs if c >= conf_th)


def cmd_score(a):
    used = used_clips()
    for item in ("침입", "배회"):
        info = clip_info(item)
        for exp in a.exps:
            dd = OUT / f"{exp}_{a.imgsz}" / SUB[item]
            files = sorted(dd.glob("*.jsonl"))
            if not files:
                print(f"\n== {item} · {exp}: 덤프 없음 ({dd})")
                continue
            rows = {f.stem: [json.loads(l) for l in f.read_text().splitlines()] for f in files}
            clips = [s for s in rows if s in info and info[s][1] is not None]
            gt = {s: info[s][1] for s in clips}
            splits = [("전체", clips), ("본 편(라벨 프레임 있음)", [s for s in clips if s in used]),
                      ("안 본 편", [s for s in clips if s not in used]),
                      ("안 본 편·주간", [s for s in clips if s not in used and info[s][2] == "Day"]),
                      ("안 본 편·야간", [s for s in clips if s not in used and info[s][2] == "Night"])]
            print(f"\n== {item} · {exp} · 해상도 {a.imgsz} · 덤프 {len(clips)}편")
            print("   %-32s" % "규칙" + "".join("  %-26s" % f"{n}({len(c)})" for n, c in splits))
            for rname, fn in RULES[item]:
                sa = {}
                for s in clips:
                    try:
                        sa[s] = fn(rows[s], info[s][0])
                    except Exception as e:      # 한 편이 깨져도 표는 낸다
                        sa[s] = None
                        print("   !", s, e)
                line = "   %-32s" % rname
                for _n, c in splits:
                    if not c:
                        line += "  %-26s" % "-"; continue
                    f1, tp, fn_, fp = kisa(gt, sa, c, TAG[item])
                    line += "  %-26s" % ("%6.2f (%s/%s/%s)" % (f1, tp, fn_, fp))
                print(line)
                if a.detail:
                    conf_th = 0.45 if item == "침입" else 0.40
                    if "0.35" in rname:
                        conf_th = 0.35
                    bad = [s for s in clips if s not in used and not (sa.get(s) is not None and gt[s] - 2 <= sa[s] <= gt[s] + 10)]
                    causes = {}
                    for s in bad:
                        c = cause(rows[s], info[s][0], gt[s], sa.get(s), conf_th, item)
                        causes[c.split("(")[0]] = causes.get(c.split("(")[0], 0) + 1
                    print("      안 본 편 실패 %d: %s" % (len(bad), ", ".join("%s %d" % kv for kv in sorted(causes.items(), key=lambda x: -x[1]))))
                    if a.detail > 1:
                        for s in bad[:40]:
                            print("        %s %s %s" % (s, info[s][2], cause(rows[s], info[s][0], gt[s], sa.get(s), conf_th, item)))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("maps")
    d = sp.add_parser("dump"); d.add_argument("exp"); d.add_argument("--imgsz", type=int, default=1280); d.add_argument("--item", default="둘", choices=["침입", "배회", "둘"])
    s = sp.add_parser("score"); s.add_argument("exps", nargs="+"); s.add_argument("--imgsz", type=int, default=1280); s.add_argument("--detail", type=int, default=0, help="1=실패 원인 집계, 2=편별")
    a = ap.parse_args()
    {"maps": cmd_maps, "dump": cmd_dump, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()

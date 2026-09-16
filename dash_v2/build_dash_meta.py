# -*- coding: utf-8 -*-
"""통합 대시보드용 메타 생성. 4항목 배포 영상별로 GT·예측신호·구역맵·손라벨을 한 JSON 에 모은다.

데이터가 여기저기 흩어져 있어(신호는 dumps/score_tl, 트랙은 dumps, 맵은 zone_maps, 손라벨은 data/학습데이터/손라벨/full)
대시보드가 매번 헤매지 않도록 한 번 스캔해 dash_v2/dash_meta.json 으로 만든다.
영상은 서버에 있으므로 상대 경로만 담고, 실제 스트리밍은 서버가 한다.
"""
import json
import math, re, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
DEPLOY = G/"data/원본데이터/kisa_배포_검증영상/deploy_val"
MAPS = G/"data/원본데이터/kisa_배포_검증영상/zone_maps"
BEFORE, AFTER, DELAY = 2.0, 10.0, 10.0

ITEMS = {
    # 재생바 곡선. 배포 구성(앙상블)의 신호를 쓴다 - scripts/make_deploy_signal.py 가 만든다.
    # 여기를 옛 실험으로 두면 화면이 판정 근거와 다른 모델을 보여 준다(2026-09-16 에 human_full 이 그랬다).
    "방화": {"key": "fire", "dir_kw": "방화", "signal": G/"dumps/score_tl/_deploy.json"},
    "침입": {"key": "intrusion", "dir_kw": "침입", "dump": G/"dumps/intrusion_tile_v3", "zone": ["Intrusion"]},
    "배회": {"key": "loiter", "dir_kw": "배회", "dump": G/"dumps/loiter_botsort_v2", "zone": ["Loitering", "Intrusion"]},
    # 자세 1280 확률 덤프. 옛 npz(2026-09-07, 자세 640)를 쓰면 화면이 배포와 다른 곡선을 보여 준다.
    "쓰러짐": {"key": "fall", "dir_kw": "쓰러짐", "seq": G/"dumps/fall_seq_1280",
             "logits": G/"runs/fall_track/deploy_track_logits.npz"},
}

def hms(t):
    p = [int(x) for x in (t or "0:0:0").split(":")]
    while len(p) < 3: p = [0]+p
    return p[0]*3600+p[1]*60+p[2]

def gt_of(xml_path):
    """GT XML 에서 알람 시각·지속·날씨 등을 뽑는다."""
    if not xml_path.exists(): return {}
    r = ET.parse(xml_path).getroot()
    al = r.find(".//Alarm") or r.find(".//AlarmEvent")
    out = {"tod": r.findtext(".//TimeOfDay") or "", "duration": r.findtext(".//Duration") or "",
           "scenario": r.findtext(".//Scenario") or ""}
    st = r.findtext(".//StartTime")
    out["gt"] = hms(st) if st else None
    dur = r.findtext(".//AlarmDuration")
    out["gt_dur"] = hms(dur) if dur else 0
    for w in ("Snow", "Fog", "Rain"):
        v = r.findtext(f".//{w}")
        if v and v.lower() not in ("no", "none"): out.setdefault("weather", []).append(w)
    return out

def zone_of(stem, tags):
    loc = "_".join(stem.split("_")[:2])
    f = MAPS/(loc+".map")
    if not f.exists(): return {}
    root = ET.parse(f).getroot()
    out = {}
    da = root.find("DetectArea")
    if da is not None:
        out["detect"] = [[int(v) for v in p.text.split(",")] for p in da.findall("Point")]
    for tag in tags:
        node = root.find(tag)
        if node is not None:
            out["zone"] = [[int(v) for v in p.text.split(",")] for p in node.findall("Point")]
            out["zone_tag"] = tag
            break
    return out

def videos_of(dir_kw):
    d = next((p for p in DEPLOY.iterdir() if p.name.startswith(dir_kw)), None)
    if not d: return []
    return sorted((d/"배포").glob("*.mp4"))

def build_fire():
    sig = json.load(open(ITEMS["방화"]["signal"], encoding="utf-8"))
    # 손라벨: 클립별 프레임·박스
    labels = json.load(open(G/"data/학습데이터/손라벨/fire_labels.json", encoding="utf-8"))
    by_clip = {}
    for r in labels:
        by_clip.setdefault(r["clip"], []).append(r)
    rows = []
    for v in videos_of("방화"):
        stem = v.stem
        s = sig.get(stem, {})
        g = gt_of(v.with_suffix(".xml"))
        rows.append({"name": stem, "video": str(v.relative_to(G)),
                     "gt": s.get("gt", g.get("gt")), "gt_dur": g.get("gt_dur", 20),
                     "tod": g.get("tod"), "weather": g.get("weather", []),
                     "signal": s.get("rows", []),   # [[t, fire, smoke]]
                     "tracks": load_dump(G/"dumps/fire_box", stem), "framew": 1280, "frameh": 720,
                     "signal_type": "fire_smoke"})
    return rows

def load_dump(folder, stem):
    f = folder/(stem+".jsonl")
    if not f.exists(): return []
    return [json.loads(l) for l in f.read_text().splitlines()]

def build_person(item):
    cfg = ITEMS[item]
    rows = []
    for v in videos_of(cfg["dir_kw"]):
        stem = v.stem
        g = gt_of(v.with_suffix(".xml"))
        z = zone_of(stem, cfg["zone"])
        dump = load_dump(cfg["dump"], stem)
        # 트랙: [{t, boxes:[[id,conf,x1,y1,x2,y2]]}] → 신호는 프레임별 최고 conf
        sig = [[r["t"], max((b[1] for b in r["boxes"]), default=0.0)] for r in dump]
        rows.append({"name": stem, "video": str(v.relative_to(G)),
                     "gt": g.get("gt"), "gt_dur": g.get("gt_dur", 10),
                     "tod": g.get("tod"), "weather": g.get("weather", []),
                     "zone": z.get("zone", []), "zone_tag": z.get("zone_tag", ""),
                     "detect": z.get("detect", []), "framew": 1280, "frameh": 720,
                     "tracks": dump, "signal": sig, "signal_type": "person"})
    return rows

def fall_curves_1280(stem):
    """배포와 같은 자세 1280 확률 곡선. 없으면 None 을 돌려 옛 npz 로 넘어간다."""
    f = ITEMS["쓰러짐"]["seq"]/(stem+".json")
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for c in d.get("curves", []):
        out.append([[round(t,1), round(1/(1+math.exp(-z)),3)] for t,z in c])
    return out


def build_fall():
    d = np.load(ITEMS["쓰러짐"]["logits"])
    names = sorted({k.split("__")[0] for k in d.files})
    rows = []
    for v in videos_of("쓰러짐"):
        stem = v.stem
        g = gt_of(v.with_suffix(".xml"))
        c1280 = fall_curves_1280(stem)
        if c1280 is not None:
            rows.append({"name": stem, "video": str(v.relative_to(G)),
                         "gt": g.get("gt"), "gt_dur": g.get("gt_dur", 0),
                         "tod": g.get("tod"), "weather": g.get("weather", []),
                         "curves": c1280, "signal_type": "fall"})
            continue
        if stem in names:
            n = int(d[f"{stem}__n"][0])
            curves = []
            for i in range(n):
                t = d[f"{stem}__t{i}"].tolist(); z = d[f"{stem}__z{i}"].tolist()
                curves.append([[round(a,1), round(1/(1+np.exp(-b)),3)] for a,b in zip(t,z)])
            gt = float(d[f"{stem}__gt"][0])
        else:
            curves = []; gt = g.get("gt")
        rows.append({"name": stem, "video": str(v.relative_to(G)),
                     "gt": gt if gt and gt>=0 else g.get("gt"), "gt_dur": g.get("gt_dur", 0),
                     "tod": g.get("tod"), "weather": g.get("weather", []),
                     "curves": curves, "signal_type": "fall"})
    return rows


def build_labelset():
    """손라벨 클립(연구개발 방화 75클립). 프레임 목록 + 박스. 영상 없이 프레임 이미지로 검수."""
    import collections
    labels = json.load(open(G/"data/학습데이터/손라벨/fire_labels.json", encoding="utf-8"))
    # 프레임 이미지 목록. scripts/make_full.py 가 만든다. 안 만들었으면 이 탭만 비우고 넘어간다.
    # (예전에는 여기서 멈춰 dash_meta.json 전체가 09-08 판에 묶여 있었다. 2026-09-16)
    mf = G/"data/학습데이터/손라벨/full/meta.json"
    if not mf.exists():
        print(f"  [건너뜀] 손라벨 탭: {mf} 없음 (scripts/make_full.py 로 만든다)", flush=True)
        return []
    lmeta = json.load(open(mf, encoding="utf-8"))
    by_clip = collections.defaultdict(lambda: {"frames": {}, "boxes": 0})
    for m in lmeta:
        by_clip[m["clip"]]["frames"].setdefault(m["file"], {"gt": m.get("gt"), "t": m.get("t"),
                                                             "W": m.get("W", 1280), "H": m.get("H", 720), "boxes": []})
    for r in labels:
        c = by_clip[r["clip"]]["frames"].get(r["file"])
        if c is not None:
            c["boxes"].append([r["cls"], r["x"], r["y"], r["w"], r["h"]])
        by_clip[r["clip"]]["boxes"] += 1
    rows = []
    for clip, d in sorted(by_clip.items()):
        frames = [{"file": f, **info} for f, info in sorted(d["frames"].items())]
        rows.append({"name": clip, "video": "", "gt": None, "signal_type": "labelset",
                     "frames": frames, "box_count": d["boxes"], "frame_count": len(frames)})
    return rows

def main():
    data = {"items": {}}
    # 예측 알람(sa)은 제출 도구의 규칙으로 서버에서 계산해 싣는다.
    # 화면이 따로 구현하면 상수가 낡아 정검/오검/미검이 실측과 달라진다(2026-09-16 에 네 항목 다 그랬다).
    import dash_sa
    data["items"]["fire"] = {"title": "방화", "rows": dash_sa.attach("방화", build_fire())}
    data["items"]["intrusion"] = {"title": "침입", "rows": dash_sa.attach("침입", build_person("침입"))}
    data["items"]["loiter"] = {"title": "배회", "rows": dash_sa.attach("배회", build_person("배회"))}
    data["items"]["fall"] = {"title": "쓰러짐", "rows": dash_sa.attach("쓰러짐", build_fall())}
    data["items"]["labelset"] = {"title": "손라벨(연구개발)", "rows": build_labelset()}
    out = G/"dash_v2/dash_meta.json"
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    for k, v in data["items"].items():
        print(f"  {v['title']}: {len(v['rows'])}편")
    print(f"저장 {out} ({out.stat().st_size//1024}KB)")

if __name__ == "__main__":
    main()

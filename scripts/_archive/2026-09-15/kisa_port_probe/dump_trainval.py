"""학습용 연구개발 사람영상(침입170·배회325)으로 '규칙 검증 전용' 덤프를 만든다.
한 번 떠 두면 규칙 파라미터 스윕을 GPU 없이 몇 초에 반복할 수 있다.
구역 다각형과 정답 시각은 각 클립의 xml 안에 들어 있다."""
import json, os, sys, time, glob, argparse, xml.etree.ElementTree as ET
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools"); import kisa_items as K
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"; SRC = f"{V}/data/원본데이터/kisa_연구개발_사람영상"
DIRS = {"intrusion": "2. 침입(170개)", "loitering": "1. 배회(325개)"}
TAG = {"intrusion": "Intrusion", "loitering": "Loitering"}

def meta_of(xml):
    r = ET.parse(xml).getroot()
    node = r.find(f".//{TAG[ITEM]}")
    if node is None: node = r.find(".//DetectArea")
    zone = [tuple(int(float(v)) for v in p.text.split(",")) for p in node.findall("Point")] if node is not None else None
    a = r.find(".//Alarm")
    if a is None or not a.findtext("StartTime"): return None
    h, m, s = a.findtext("StartTime").split(":")
    return dict(zone=zone, gt=int(h)*3600+int(m)*60+int(s),
                tod=(r.findtext(".//TimeOfDay") or "?").strip(),
                snow=(r.findtext(".//Snow") or "?").strip(), rain=(r.findtext(".//Rain") or "?").strip(),
                fog=(r.findtext(".//Fog") or "?").strip(), loc=(r.findtext(".//Location") or "?").strip())

ap = argparse.ArgumentParser(); ap.add_argument("--item", required=True); ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args(); ITEM = a.item
OUT = f"{V}/dumps/trainval_{ITEM}"; os.makedirs(OUT, exist_ok=True)
cfg = K.ITEMS[ITEM]
det = K.PersonDetector(K.WEIGHTS / cfg["model"], contain=None) if ITEM == "intrusion" else None
metas = {}
xmls = sorted(glob.glob(f"{SRC}/{DIRS[ITEM]}/*.xml"))
if a.limit: xmls = xmls[:a.limit]
t0 = time.time()
for i, x in enumerate(xmls, 1):
    stem = os.path.basename(x)[:-4]; mp4 = x[:-4] + ".mp4"; out = f"{OUT}/{stem}.jsonl"
    m = meta_of(x)
    if m is None or not os.path.exists(mp4): print(f"  건너뜀 {stem}", flush=True); continue
    metas[stem] = m
    if os.path.exists(out) and os.path.getsize(out) > 0:                  # 재실행 시 이어서
        continue
    bs = K.BotSortPersons(K.WEIGHTS / cfg["model"]) if ITEM == "loitering" else None
    trk = K.Tracker() if bs is None else None
    src = K.FileSource([mp4], stride_s=0.5); n = 0
    with open(out + ".tmp", "w") as w:
        while True:
            f = src.read()
            if f is None: break
            boxes = bs.update(f.bgr) if bs else trk.update(det.detect(f.bgr))
            w.write(json.dumps({"t": round(f.ts, 2), "boxes": [list(b) for b in boxes]}) + "\n"); n += 1
    os.replace(out + ".tmp", out)
    el = time.time() - t0
    print(f"  [{i}/{len(xmls)}] {stem} 표본{n} ({el/60:.1f}분 경과, 예상 총 {el/i*len(xmls)/60:.0f}분)", flush=True)
    json.dump(metas, open(f"{OUT}/_meta.json", "w"), ensure_ascii=False)
json.dump(metas, open(f"{OUT}/_meta.json", "w"), ensure_ascii=False)
print(f"완료 {len(metas)}편 → {OUT}", flush=True)

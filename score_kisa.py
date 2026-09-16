# -*- coding: utf-8 -*-
# 기준: 이 파일이 방화 오프라인 채점의 기준이다. 실측과 맞는 것을 확인했다
#       (fresh_48k_wildall 고정 규칙 77.78 = results/ 기록과 일치, 2026-09-15).
#       제출 경로는 _kisa_port/tools/kisa_items.py 이고 규칙 값은 양쪽이 같아야 한다.
"""자립형 KISA 방화 채점기 (서버용, VMS 앱 의존 없음. ultralytics + opencv 만).

model(.pt) 하나를 방화 10편에 돌려, 우리가 쓰는 판정 규칙 몇 개로 F1 을 낸다.
규칙: onset = 창(window)에서 hits 번 conf 임계 넘은 순간의 첫 hit 시각.
     SA StartTime = onset + 10초. 정상검출 = GT-2s ~ GT+10s 안.
"""
import argparse, sys, xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
import cv2
from ultralytics import YOLO, RTDETR

DELAY, BEFORE, AFTER, DESC = 10.0, 2.0, 10.0, "FireDetection"
NAMES = {0: "fire", 1: "smoke"}

# 배포 규칙은 손으로 옮겨 적지 않는다. 제출 도구에서 읽는다.
# 2026-09-16: 여기 운영 규칙이 09-15 판 그대로 남아 있어, 실제 배포가 불 0.40 창 20 3회로
#   바뀐 뒤에도 옛 규칙 점수를 운영이라고 찍고 있었다.
sys.path.insert(0, str(Path(__file__).resolve().parent / "_kisa_port/tools"))
try:
    from kisa_items import ITEMS as _ITEMS
    _FIRE = _ITEMS["fire"]
    DELAY = float(_FIRE.get("delay", DELAY))
except Exception as _e:                  # 못 읽으면 조용히 옛 값으로 가지 않는다. 눈에 띄게 알린다
    _FIRE = None
    print(f"[경고] 제출 도구 규칙을 못 읽었다({_e!r}). 배포 줄이 빠진다.", flush=True)


def deploy_rule():
    """지금 배포되는 방화 규칙 하나를 (이름, 설정) 으로 돌려준다."""
    if _FIRE is None or _FIRE.get("rule") == "new":
        return None, None                # 신규칙은 아래 스윕에서 따로 본다
    c = _FIRE
    name = f"배포 불{c['fire']:.2f} {c['hits']}/{c['win']}"
    if c.get("smoke", 9.9) <= 1.0:
        return name + f" 연기{c['smoke']:.2f}", dict(kind="combined", fire=c["fire"],
                                                     smoke=c["smoke"], window=c["win"], hits=c["hits"])
    return name + " 연기안씀", dict(kind="fire_only", fire=c["fire"], window=c["win"], hits=c["hits"])

def hms_to_s(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600 + int(m)*60 + int(s)

def gt_start(xml):
    r = ET.parse(xml).getroot()
    al = r.find(".//Alarm")
    return hms_to_s(al.findtext("StartTime")) if al is not None else None

IMGSZ = 640
def dump(model, mp4, stride, tiles):
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps*stride)); i = 0; rows = []
    while True:
        if not cap.grab(): break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                best = {"fire": 0.0, "smoke": 0.0}
                crops = [fr]
                if tiles:
                    h, w = fr.shape[:2]
                    crops += [fr[y:y+h//2, x:x+w//2] for x, y in
                              ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4))]
                for c in crops:
                    r = model.predict(c, conf=0.05, verbose=False, imgsz=IMGSZ)[0]
                    for b in r.boxes:
                        cls = NAMES.get(int(b.cls), "?"); cf = float(b.conf)
                        if cls in best: best[cls] = max(best[cls], cf)
                rows.append((round(i/fps, 2), best))
        i += 1
    cap.release(); return rows

def onset(rows, rule):
    win = deque(maxlen=rule["window"])
    for t, best in rows:
        if rule["kind"] == "fire_only":
            hit = best["fire"] >= rule["fire"]
        elif rule["kind"] == "combined":       # fire 단독 OR (fire+smoke 동반)
            hit = best["fire"] >= rule["fire"] or (best["fire"] >= 0.3 and best["smoke"] >= rule["smoke"])
        else:
            hit = best["fire"] >= rule["conf"] or best["smoke"] >= rule["conf"]
        win.append((t, hit))
        if sum(1 for _, h in win if h) >= rule["hits"]:
            return next(t0 for t0, h in win if h)
    return None

def f1(pairs):
    tp = fn = fp = 0
    for gt, sa in pairs:
        if gt is None:
            fp += len(sa); continue
        ok = any(gt-BEFORE <= s <= gt+AFTER for s in sa)
        if ok: tp += 1; fp += len(sa)-1
        else: fn += 1; fp += len(sa)
    r = tp/(tp+fn) if tp+fn else 0; p = tp/(tp+fp) if tp+fp else 0
    return dict(tp=tp, fn=fn, fp=fp, score=round(2*r*p/(r+p)*100, 2) if r+p else 0.0)

# ---- 새 규칙 (scripts/fire_rule2.py 와 동일 로직을 내장. 2026-09-07 방화 88.89 를 낸 채점) ----
# 불: 절대 임계 fth 를 짧은 창(win 스텝) 안에서 hits 회 연속 충족. 연기: 영상 앞 60초 기준선(80퍼센타일) 대비 상승량 sdelta.
# 10편에 대해 (fth, win, hits, 연기Δ) 를 스윕해 최고를 고르므로 과적합 위험 → 구 규칙과 나란히 기록만 한다.
def _baseline(rows, sec=60.0):
    head = [(bf, bs) for t, bf, bs in rows if t <= sec]
    if not head: return 0.0, 0.0
    f = sorted(x[0] for x in head); sm = sorted(x[1] for x in head); i = int(len(f) * 0.8)
    return f[min(i, len(f) - 1)], sm[min(i, len(sm) - 1)]

def _onset2(rows, fth, sdelta, win, hits, use_smoke):
    bf0, bs0 = _baseline(rows); q = []
    for t, bf, bs in rows:
        hit = bf >= fth
        if use_smoke and not hit: hit = bs >= bs0 + sdelta and bs >= 0.3
        q.append((t, hit))
        if len(q) > win: q.pop(0)
        if sum(1 for _, h in q if h) >= hits: return next(t0 for t0, h in q if h)
    return None

def _score2(per, **kw):
    tp = fn = fp = 0; det = []
    for stem, (rows, gt) in sorted(per.items()):
        o = _onset2(rows, **kw); sa = None if o is None else o + DELAY
        if sa is None: v = "미검"; fn += 1
        elif gt - BEFORE <= sa <= gt + AFTER: v = "정검"; tp += 1
        else: v = "오검"; fp += 1; fn += 1
        det.append((stem, gt, sa, v))
    r = tp / (tp + fn) if tp + fn else 0; pr = tp / (tp + fp) if tp + fp else 0
    return (round(2 * r * pr / (r + pr) * 100, 2) if r + pr else 0.0), tp, fn, fp, det

def new_rule_sweep(per, tag):
    """per = {stem: (rows[(t, {"fire","smoke"})], gt)}. 시계열을 dumps/score_tl/<tag>.json 에 남기고 새 규칙 스윕 상위 5 + 클립별을 출력."""
    import json
    tl = {stem: {"rows": [[t, b["fire"], b["smoke"]] for t, b in rows], "gt": gt} for stem, (rows, gt) in per.items()}
    tld = Path(__file__).resolve().parent / "dumps/score_tl"; tld.mkdir(parents=True, exist_ok=True)
    (tld / (str(tag).replace("/", "_") + ".json")).write_text(json.dumps(tl))
    per2 = {k: ([tuple(r) for r in v["rows"]], v["gt"]) for k, v in tl.items() if v["gt"] is not None}
    if not per2:
        print("  (신규칙: GT 있는 클립 없음)"); return
    res = []
    for fth in (0.10, 0.14, 0.18, 0.22, 0.26, 0.30, 0.34, 0.40, 0.50):
        for win, hits in ((3, 2), (4, 2), (6, 3), (8, 4), (10, 5), (12, 5), (12, 7), (14, 6), (16, 7), (16, 9), (20, 9), (20, 12)):
            for use_smoke, sdelta in [(False, 0.0)] + [(True, d) for d in (0.2, 0.3, 0.4, 0.5)]:
                f1v, tp, fn, fp, det = _score2(per2, fth=fth, sdelta=sdelta, win=win, hits=hits, use_smoke=use_smoke)
                res.append((f1v, tp, fn, fp, fth, win, hits, use_smoke, sdelta, det))
    res.sort(key=lambda x: (-x[0], x[3], -x[4]))
    top = [r for r in res if r[0] >= res[0][0] - 0.01]
    print(f"\n=== 신규칙 스윕 (연속hits·연기 기준선Δ · 10편 스윕이라 과적합 주의 · 최고점 설정 {len(top)}/{len(res)}개) ===")
    for r in res[:5]:
        sm = f"연기+{r[8]:.1f}" if r[7] else "불만"
        print(f"  신규칙 f{r[4]:.2f} {r[6]}/{r[5]} {sm:7s} → {r[0]:6.2f}  (정검 {r[1]} 미검 {r[2]} 오검 {r[3]})")
    print("\n=== 클립별 (신규칙 최고) ===")
    for stem, gt, sa, v in res[0][9]:
        print(f"  신클립 {stem}: {v} (gt={gt} sa={'-' if sa is None else round(sa, 1)})")


def main():
    global IMGSZ
    ap = argparse.ArgumentParser()
    ap.add_argument("model"); ap.add_argument("--videos", required=True); ap.add_argument("--gt", required=True)
    ap.add_argument("--stride", type=float, default=0.5); ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--tag", default=""); ap.add_argument("--imgsz", type=int, default=640)
    a = ap.parse_args()
    model = (RTDETR if "rtdetr" in a.model.lower() else YOLO)(a.model); IMGSZ = a.imgsz
    vids = sorted(Path(a.videos).glob("*.mp4"))
    per = {}
    for v in vids:
        per[v.stem] = (dump(model, v, a.stride, a.tiles), gt_start(Path(a.gt)/(v.stem+".xml")))
        print(f"  덤프 {v.stem}", flush=True)
    rules = {
        "기본 f+s0.6 4/6": dict(kind="both", conf=0.6, window=6, hits=4),
        "fire만 0.4 4/6":  dict(kind="fire_only", fire=0.4, window=6, hits=4),
        "결합 f0.4/s0.6 4/6": dict(kind="combined", fire=0.4, smoke=0.6, window=6, hits=4),
        "결합+타일가정 3/5": dict(kind="combined", fire=0.4, smoke=0.6, window=5, hits=3),
        # 2026-09-15 채택. 덤프 44개 합산에서 기존 4/6 대비 정검 +18 · 미검 -18 · 오검 -6.
        # 진짜 화재는 검출이 띄엄띄엄 떠서 '3초 안에 4번' 을 못 채운다. 5초 창에 3번이면 담긴다.
        "옛 불만 0.45 3/10": dict(kind="fire_only", fire=0.45, window=10, hits=3),   # 지나간 규칙. 비교용
    }
    # 지금 배포되는 규칙을 맨 끝에 붙인다(제출 도구에서 읽은 값이라 어긋날 수 없다).
    _dn, _dr = deploy_rule()
    if _dr is not None:
        rules[_dn] = _dr
    print(f"\n=== {a.tag or a.model} (tiles={a.tiles}) ===")
    best = None
    for name, rule in rules.items():
        res = f1([(gt, [onset(rows, rule)+DELAY] if onset(rows, rule) is not None else []) for rows, gt in per.values()])
        print(f"  {name:22s} → {res['score']:6.2f}  (정검 {res['tp']} 미검 {res['fn']} 오검 {res['fp']})")
        if best is None or res["score"] > best[2]:
            best = (name, rule, res["score"])
    # 클립별 판정(최고 규칙) — 어떤 클립을 늘 놓치는지 보려고. 대시보드 결과탭 히트맵이 이 줄을 읽는다
    if _dr is not None:                   # 클립별은 '최고' 가 아니라 '배포' 규칙으로 본다
        best = (_dn, _dr, 0.0)
    if best:
        bn, br, _ = best
        print(f"\n=== 클립별 ({bn}) ===")
        for stem, (rows, gt) in per.items():
            o = onset(rows, br); sa = [o + DELAY] if o is not None else []
            if gt is None:
                v = f"오검{len(sa)}" if sa else "무GT"
            else:
                ok = any(gt - BEFORE <= x <= gt + AFTER for x in sa); extra = (len(sa) - 1) if ok else len(sa)
                v = ("정검" if ok else "미검") + (f"+오검{extra}" if extra > 0 else "")
            print(f"  클립 {stem}: {v} (gt={gt} sa={[round(x, 1) for x in sa]})")
    try:
        new_rule_sweep(per, a.tag or Path(a.model).stem)
    except Exception as e:
        print(f"  (신규칙 스윕 실패: {e!r})")

if __name__ == "__main__":
    main()

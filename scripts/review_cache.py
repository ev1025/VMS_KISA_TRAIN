# -*- coding: utf-8 -*-
"""영상 검수 탭용 미리 계산 (2026-09-28).

검수 화면이 모델을 누를 때마다 그 자리에서 추론하던 것을 없앤다. 끝난 판을 여기서 미리 돌려 저장하고,
화면(dash_v2 /api/review_*)은 저장된 파일만 읽는다.

대상: '지금 데이터' 로 COCO 사전학습부터 학습해 끝난 판만
  - 사람: 학습 데이터 이름(base · oversample · extras)이 전부 hnfix 계열(09-27 바로잡은 사람 라벨)
  - 방화: KISA 쪽 데이터가 전부 09-26 방화 라벨 이후(외부 공개셋 aihub · fasdd · wildfire · azimjaan 은 상관없음)
  - 이어 학습(옛 판 가중치에서 시작) · 배포 가중치 · 도는 판은 뺀다
  - 체크포인트는 best · last 둘 다, 해상도는 그 판의 학습 해상도(작업 PC 채점과 같게)

계산: _kisa_port/tools/kisa_items.py 의 검출기 · 추적기 · 규칙을 그대로 불러 쓴다(복사하지 않는다).
  침입 = PersonDetector(3x3 타일) + Tracker + IntrusionRule
  배회 = BotSortPersons(전체 프레임 추적) + LoiterRule
  방화 = FireJudge(6뷰). 박스는 FireJudge 가 부르는 predict 를 가로채 모은다
  채점은 경보가 확정되면 그 뒤 프레임을 추론하지 않는다. 검수 화면은 영상 끝까지 박스가 있어야 하므로
  추론은 끝까지 하고, 규칙에는 경보 확정 전까지만 먹인다(채점과 같은 경보 시각).

출력: dumps/review/<실험>/<best|last>/<항목>/<클립>.json 과 summary.json(편별 경보 · 판정 · 점수)
쓰는 법: .venv/bin/python scripts/review_cache.py [--once] [--only <실험>] [--limit N] [--verify]
  기본은 10분마다 새로 끝난 판을 찾아 계속 돈다(tmux 에 한 개만 띄운다. 서버 A 에 조사용 파이썬 여러 개 금지)
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kisa_paths as KP                                    # noqa: E402

OUT = KP.V / "dumps/review"
ITEM_OF = {"방화": "fire", "침입": "intrusion", "배회": "loitering"}   # kisa_items.py 항목명 = 저장 폴더명
EXTERNAL = ("aihub", "fasdd", "wildfire", "azimjaan")      # 방화 외부 공개셋(우리 라벨과 무관)
FIRE_FROM = 20260926                                       # 방화 '지금 데이터' = 09-26 방화 라벨부터
CKPTS = ("best", "last")
LOOP_S = 600
KST = timezone(timedelta(hours=9))                         # 서버 시계는 UTC 다. 기록은 한국 시각으로


def now(fmt="%Y-%m-%d %H:%M:%S"):
    return datetime.now(KST).strftime(fmt)


# ---------------------------------------------------------------- 대상 판 고르기(화면 서버도 이것을 import 한다)
def _datasets(m):
    names = [m.get("base")] + list((m.get("oversample") or {}).keys()) + list(m.get("extras") or [])
    return [n for n in names if n]


def _current(m):
    """이 판의 학습 데이터가 전부 '지금 데이터' 인가."""
    names = _datasets(m)
    if not names:
        return False
    if m.get("item") == "방화":
        for n in names:
            if n.startswith(EXTERNAL):
                continue
            d = re.search(r"(20\d{6})$", n)
            if not d or int(d.group(1)) < FIRE_FROM:
                return False
        return True
    return all("hnfix" in n for n in names)


def eligible():
    """[(실험, meta)] 끝난 순서 최신 먼저. 조건은 이 파일 머리말."""
    out = []
    for mj in (KP.V / "results").glob("*/meta.json"):
        try:
            m = json.loads(mj.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        pt = Path(m.get("best_pt") or "")
        if m.get("status") != "trained" or not m.get("ended") or not pt.is_file():
            continue
        if not str(m.get("model") or "").startswith("yolo"):          # 이어 학습 판은 옛 판 가중치에서 시작한다
            continue
        if m.get("item") not in ("방화", "사람", "침입", "배회") or not _current(m):
            continue
        out.append((mj.parent.name, m))
    out.sort(key=lambda x: x[1].get("ended") or "", reverse=True)
    return out


def items_of(m):
    """배회를 침입보다 먼저 한다(배회는 표본마다 추론 한 번, 침입은 3x3 타일이라 아홉 번)."""
    return ["방화"] if m.get("item") == "방화" else sorted(KP.PERSON_ITEMS, key=lambda i: i != "배회")


def weights(m, ckpt):
    best = Path(m["best_pt"])
    return best if ckpt == "best" else best.with_name("last.pt")


def res_of(m):
    return int((m.get("train") or {}).get("imgsz") or KP.DEFAULT_IMGSZ)


def cache_dir(exp, ckpt, item):
    return OUT / exp / ckpt / item


def clips(item_ko):
    return sorted(KP.videos(item_ko).glob("*.mp4"))


def is_done(exp, m, ckpt, item_ko):
    s = cache_dir(exp, ckpt, ITEM_OF[item_ko]) / "summary.json"
    if not s.is_file():
        return False
    try:
        j = json.loads(s.read_text(encoding="utf-8"))
        w = weights(m, ckpt)
        return j.get("weights_mtime") == int(w.stat().st_mtime) and len(j.get("clips") or {}) == len(clips(item_ko))
    except Exception:
        return False


# ---------------------------------------------------------------- 계산
def _K(tools=None):
    sys.path.insert(0, str(tools or (KP.V / "_kisa_port/tools")))
    import kisa_items as K                                  # 판정 규칙 · 실행 코드 단일 기준
    return K


def _r(v, n=1):
    return round(float(v), n)


def _verdict(K, gt0, sa):
    if gt0 is not None and sa is not None and gt0 - K.BEFORE_S <= sa <= gt0 + K.AFTER_S:
        return "정검"
    return "미검" if sa is None else "오검"


class _Rec:
    """FireJudge 가 부르는 model.predict 를 그대로 통과시키며 박스를 모은다. 조각의 원점은 원본 프레임 안의 위치로 구한다."""

    def __init__(self, model):
        self.m, self.frame, self.boxes = model, None, []

    def predict(self, img, **kw):
        res = self.m.predict(img, **kw)
        off = img.ctypes.data - self.frame.ctypes.data       # 조각은 원본 프레임을 자른 뷰다
        y, rem = divmod(off, self.frame.strides[0])
        x = rem // self.frame.strides[1]
        for b in res[0].boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            self.boxes.append([int(b.cls[0]), _r(b.conf[0], 3), _r(x1 + x), _r(y1 + y), _r(x2 + x), _r(y2 + y)])
        return res


def run_clip(K, item, mp4, pt, res, device=None, maps=None):
    """영상 한 편. 반환 = 화면에 줄 dict. 영상을 끝까지 못 읽었으면 RuntimeError(가짜 판정을 남기지 않는다)."""
    maps = maps or KP.ZONE_MAPS
    cfg = dict(K.ITEMS[item])
    stem = mp4.stem
    src = K.FileSource([mp4], stride_s=cfg["stride"])
    samples, signal = [], []
    onset, judge, det, tracker, poly, wh = None, None, None, None, None, None
    rec = None
    while True:
        f = src.read()
        if f is None:
            break
        if judge is None:                                   # 첫 프레임에서 채점기(process)와 같은 순서로 준비
            wh = (f.bgr.shape[1], f.bgr.shape[0])
            if item == "fire":
                judge = K.FireJudge([(pt, res)], cfg, device)
                rec = _Rec(judge.models[0][0])
                judge.models = [(rec, judge.models[0][1])]
            elif item == "loitering":
                tracker = K.BotSortPersons(pt, device=device, imgsz=res)
                judge = K.make_judge(item, cfg, stem, maps, wh, None)
            else:
                tile = dict(K.TILE); tile["imgsz"] = res                   # 작업 PC 채점의 --person-imgsz 와 같다
                det = K.PersonDetector(pt, tile=tile, device=device, contain=None)
                tracker = K.Tracker()
                judge = K.make_judge(item, cfg, stem, maps, wh, det)
            poly = getattr(judge, "poly", None)
        t = f.ts
        if item == "fire":
            rec.frame, rec.boxes = f.bgr, []
            if onset is not None:
                judge.decided = None                        # 경보 뒤에도 화면용으로 계속 추론한다(경보 시각은 처음 것)
            d = judge.feed(t, f.bgr)
            if onset is None and d is not None:
                onset = d
            _, fmax, smax = judge.rows[-1]
            samples.append([_r(t, 2), rec.boxes])
            signal.append([_r(t, 2), _r(fmax, 3), _r(smax, 3)])
            continue
        if item == "loitering":
            boxes = tracker.update(f.bgr)
        else:
            boxes = tracker.update(det.detect(f.bgr))
        if onset is None:
            onset = judge.feed(t, boxes)
        inside = []
        for pid, conf, x1, y1, x2, y2 in boxes:            # 신호 = 규칙이 '구역 안' 으로 치는 사람의 최고 확신도
            b = (x1, y1, x2, y2)
            ok = K.entered(b, poly, cfg["corners"])
            if ok and cfg.get("margin"):
                ok = K.foot_inside(b, poly, cfg["margin"])
            if ok:
                inside.append(conf)
        samples.append([_r(t, 2), [[int(pid), _r(c, 3), _r(a), _r(b_), _r(x), _r(y)] for pid, c, a, b_, x, y in boxes]])
        signal.append([_r(t, 2), _r(max(inside), 3) if inside else 0.0])
    import cv2                                               # 끝까지 읽었나: 외장 드라이브가 빠지면 조용히 짧게 끝나 가짜 판정이 된다(2026-09-28)
    cap = cv2.VideoCapture(str(mp4)); n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0; fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; cap.release()
    want = int(-(-n // max(1, int(round(fps * cfg["stride"]))))) if n else 0
    if not want or len(samples) < want - 2:
        raise RuntimeError(f"{stem}: 표본 {len(samples)}/{want} (영상을 끝까지 못 읽음)")
    o = onset if onset is not None else (judge.final() if judge else None)
    sa = None if o is None else _r(o + cfg["delay"], 2)
    xml = mp4.with_suffix(".xml")
    gts = K.read_alarms(xml) if xml.is_file() else []
    gt0 = gts[0]["start_s"] if gts else None
    return {"clip": stem, "item": item, "res": res, "stride": cfg["stride"], "wh": wh,
            "zone": [list(p) for p in poly] if poly else None,
            "conf": cfg.get("conf", cfg.get("fire")), "smoke": cfg.get("smoke"),
            "samples": samples, "signal": signal, "alarm": sa, "gt": gt0, "verdict": _verdict(K, gt0, sa),
            "_pair": (gts, [{"start_s": sa, "desc": cfg["desc"]}] if sa is not None else [])}


def build(K, exp, m, ckpt, item_ko, limit=None, device=None, vids=None, maps=None, pt=None, out=None, wmtime=None, put=None, where="서버 A"):
    """한 판 · 한 체크포인트 · 한 항목. 다른 장비(작업 PC)에서 돌릴 때는 영상 · 영역 · 가중치 · 출력 위치와
    서버 가중치 시각(wmtime)을 넘기고, put(파일) 이 서버로 올린다. 이미 같은 가중치로 만든 편은 다시 안 돈다(이어하기)."""
    item = ITEM_OF[item_ko]
    wref, res = weights(m, ckpt), res_of(m)                 # summary 에 적는 가중치는 서버 기준
    pt = pt or wref
    wmtime = wmtime if wmtime is not None else int(wref.stat().st_mtime)
    d = out or cache_dir(exp, ckpt, item)
    d.mkdir(parents=True, exist_ok=True)
    vids = vids or clips(item_ko)
    vids = vids[:limit] if limit else vids
    rows, pairs, t0 = {}, [], time.time()
    for i, mp4 in enumerate(vids):
        f = d / (mp4.stem + ".json")
        r = None
        if f.is_file() and not limit:
            try:
                old = json.loads(f.read_text(encoding="utf-8"))
                if old.get("wmtime") == wmtime and old.get("res") == res:
                    r = old
                    xml = mp4.with_suffix(".xml")
                    gts = K.read_alarms(xml) if xml.is_file() else []
                    r["_pair"] = (gts, [{"start_s": r["alarm"], "desc": K.ITEMS[item]["desc"]}] if r["alarm"] is not None else [])
            except Exception:
                r = None
        fresh = r is None
        if fresh:
            r = run_clip(K, item, mp4, pt, res, device, maps)
            r["wmtime"], r["where"] = wmtime, where
        pairs.append(r.pop("_pair"))
        if fresh:
            tmp = d / (mp4.stem + ".json.tmp")
            tmp.write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(f)                                   # 반쯤 쓴 파일을 화면이 읽지 않게
        if put:
            put(f)                                           # 이어하기로 다시 쓴 편도 올린다(서버에 없을 수 있다, 2026-09-29)
        rows[mp4.stem] = {"alarm": r["alarm"], "gt": r["gt"], "verdict": r["verdict"]}
        (d / "_progress.json").write_text(json.dumps({"done": i + 1, "total": len(vids)}), encoding="utf-8")
        if put:
            put(d / "_progress.json")
        print(f"  [{exp} {ckpt} {item}] {i + 1}/{len(vids)} {mp4.stem} {r['verdict']} (gt={r['gt']} sa={r['alarm']})", flush=True)
    s = K.score(pairs)
    summ = {"exp": exp, "ckpt": ckpt, "item": item, "res": res, "weights": str(wref), "where": where,
            "weights_mtime": wmtime, "made": now(),
            "clips": rows, "score": {"정검": s["정상검출"], "미검": s["미검출"], "오검": s["오검출"], "점수": round(s["점수"], 2)},
            "minutes": round((time.time() - t0) / 60, 1)}
    if not limit:                                           # 일부만 돈 시험 실행은 '끝남' 으로 남기지 않는다
        tmp = d / "summary.json.tmp"
        tmp.write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / "summary.json")
        (d / "_progress.json").unlink(missing_ok=True)
        if put:
            put(d / "summary.json")
    print(f"[{exp} {ckpt} {item}] 정검 {summ['score']['정검']} 미검 {summ['score']['미검']} 오검 {summ['score']['오검']} → {summ['score']['점수']} ({summ['minutes']}분)", flush=True)
    return summ


# ---------------------------------------------------------------- 작업 PC 채점과 대조(화면 서버도 이것을 import 한다)
RE_SEC = re.compile(r"^--- (best|last) ---")
RE_ITEM = re.compile(r"^(intrusion|loitering|fire) (\d+) \(작업 PC\): 정검 (\d+) 미검 (\d+) 오검 (\d+) → 점수 ([\d.]+)")
RE_BAD = re.compile(r"(C00_\d+_\d+) \? (미검|오검)\(gt=([\d.]+|None) sa=([\d.]+|None)\)")


def official(exp):
    """results/<실험>/score.txt 의 작업 PC 채점. {ckpt: {item: {"점수", "정검", "미검", "오검", "bad": {클립: 판정}}}}"""
    f = KP.V / "results" / exp / "score.txt"
    out, ck, it = {}, None, None
    if not f.is_file():
        return out
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        m = RE_SEC.match(ln.strip())
        if m:
            ck = m.group(1); out.setdefault(ck, {}); continue
        m = RE_ITEM.match(ln.strip())
        if m and ck:
            it = m.group(1)
            out[ck][it] = {"res": int(m.group(2)), "정검": int(m.group(3)), "미검": int(m.group(4)),
                           "오검": int(m.group(5)), "점수": float(m.group(6)), "bad": {}}
            continue
        if ck and it and "틀린 편" in ln:
            for c, v, _g, _s in RE_BAD.findall(ln):
                out[ck][it]["bad"][c] = v
    return out


def verify(exp, ckpt, item):
    """저장한 판정과 작업 PC 채점의 편별 판정이 같은가."""
    s = json.loads((cache_dir(exp, ckpt, item) / "summary.json").read_text(encoding="utf-8"))
    o = official(exp).get(ckpt, {}).get(item)
    if not o:
        print(f"  대조 불가: {exp} {ckpt} {item} 작업 PC 채점 없음"); return None
    diff = [(c, r["verdict"], o["bad"].get(c, "정검")) for c, r in s["clips"].items() if r["verdict"] != o["bad"].get(c, "정검")]
    print(f"  대조 {exp} {ckpt} {item}: 서버 {s['score']['점수']} / 작업 PC {o['점수']} · 편별 다름 {len(diff)} {diff}")
    return diff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="한 바퀴만")
    ap.add_argument("--only", default=None, help="이 실험만")
    ap.add_argument("--ckpt", default=None, choices=CKPTS)
    ap.add_argument("--item", default=None, choices=list(ITEM_OF), help="이 항목만(방화 · 침입 · 배회)")
    ap.add_argument("--limit", type=int, default=None, help="앞 N편만(시험 실행. summary 를 안 남긴다)")
    ap.add_argument("--verify", action="store_true", help="끝난 것마다 작업 PC 채점과 편별 대조")
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    K = None
    while True:
        todo = []
        for ck in ([a.ckpt] if a.ckpt else CKPTS):          # best 를 모든 판에서 먼저, 그다음 last
            for exp, m in eligible():
                if a.only and exp != a.only:
                    continue
                for it in items_of(m):
                    if a.item and it != a.item:
                        continue
                    if a.limit or not is_done(exp, m, ck, it):
                        todo.append((exp, m, ck, it))
        if todo:
            print(now("[%m-%d %H:%M KST]"), f"할 일 {len(todo)}개: " + ", ".join(f"{e}/{c}/{ITEM_OF[i]}" for e, _, c, i in todo), flush=True)
        for exp, m, ck, it in todo:
            if not a.limit and is_done(exp, m, ck, it):   # 그 사이 다른 장비(작업 PC)가 끝냈을 수 있다
                continue
            K = K or _K()
            try:
                build(K, exp, m, ck, it, a.limit, a.device)
            except RuntimeError as e:                     # 영상 읽기 실패 등. 다음 바퀴에 다시(이미 된 편은 이어서)
                print(now("[%m-%d %H:%M KST]"), "실패", exp, ck, it, e, flush=True)
                continue
            if a.verify and not a.limit:
                verify(exp, ck, ITEM_OF[it])
        if a.once or a.limit:
            return
        time.sleep(LOOP_S)


if __name__ == "__main__":
    main()

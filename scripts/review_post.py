# -*- coding: utf-8 -*-
"""영상 검수 '상위권' 묶음: 항목별 점수 상위 3개 판에 판정기 쪽 기술(후처리 · 규칙)을 붙인 결과(2026-09-30 사용자).
학습 없이 바로 켤 수 있는 기술은 검수 캐시(dumps/review, 판정기와 같은 초당 2장 표본의 사람 박스) 위에서 판정만 다시 돈다.
  - 박스 → (기술의 박스 후처리) → 판정기와 같은 Tracker → (번호 거르기) → 판정기와 같은 IntrusionRule(기술이 바꾼 상수)
  - 결과는 dumps/review/<실험>/<ckpt>+<기술>/<항목>/ 에 원래 캐시와 같은 모양으로 쓴다 → 화면 · API 는 그대로 읽는다
  - 기술 추가 = VARIANTS 에 한 줄. 화면 서버가 상위 3개에 없는 것을 뒤에서 계산한다(compute_missing)
  - 채점편은 측정만. 이 결과로 규칙을 고르지 않는다(규칙은 연구개발 안 본 편에서, docs/EXPERIMENTS.md)
python scripts/review_post.py --check   기술 없음(none)으로 다시 돌린 경보가 원래 캐시와 편마다 같은지(모든 판)"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_cache as RC                                   # noqa: E402

K = RC._K()
TOP_N = 3


# ---------------------------------------------------------------- 기술(박스 후처리 · 번호 거르기 · 규칙 상수)
def seam_fix(dets, W=1280, H=720, grid=3, overlap=0.2, tol=2.0):
    """타일 경계 조각 정리(09-29 밤, 서버 B calc_intr.py 와 같은 계산). 판정기 3x3 타일(겹침 0.2)이 경계에 걸친 사람을
    위 · 아래(좌 · 우) 두 조각으로 잡는다(IoU 0.5 미만이라 안 합쳐짐).
    (1) 같은 겹침 띠의 양쪽 경계에 각각 잘린 두 박스(옆으로 절반 넘게 겹침) → 합집합 하나
    (2) 경계에 잘린 박스가 더 큰 박스 안에 75% 이상 → 버림. dets = [[conf, x1, y1, x2, y2], ...]"""
    th, tw = H // grid, W // grid
    oy, ox = int(th * overlap), int(tw * overlap)
    yb = [((g + 1) * th - oy, (g + 1) * th + oy) for g in range(grid - 1)]
    xb = [((g + 1) * tw - ox, (g + 1) * tw + ox) for g in range(grid - 1)]
    near = lambda v, e: abs(v - e) <= tol
    ds = [list(d) for d in dets]
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(ds):
            for j, b in enumerate(ds):
                if i == j:
                    continue
                ov_x = min(a[3], b[3]) - max(a[1], b[1])
                ov_y = min(a[4], b[4]) - max(a[2], b[2])
                vert = any(near(a[4], hi) and near(b[2], lo) for lo, hi in yb) and a[2] < b[2] and ov_x > 0.5 * min(a[3] - a[1], b[3] - b[1])
                horz = any(near(a[3], hi) and near(b[1], lo) for lo, hi in xb) and a[1] < b[1] and ov_y > 0.5 * min(a[4] - a[2], b[4] - b[2])
                if vert or horz:
                    ds[i] = [max(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]), max(a[4], b[4])]
                    del ds[j]
                    merged = True
                    break
            if merged:
                break
    cut = lambda d: any(near(d[4], hi) or near(d[2], lo) for lo, hi in yb) or any(near(d[3], hi) or near(d[1], lo) for lo, hi in xb)
    area = lambda d: (d[3] - d[1]) * (d[4] - d[2])
    return [d for d in ds if not (cut(d) and any(o is not d and area(o) > area(d) and K.contained(d[1:], o[1:]) >= 0.75 for o in ds))]


def contain(dets):
    """겹침 제거: 판정기 PersonDetector 의 contain=0.75(작은 박스가 큰 박스 안에 75% 이상이면 버림). 지금 판정기는 끔(None)"""
    return K.nms([tuple(d) for d in dets], thr=0.5, contain=0.75)


def still_out(f=1.0):
    """안 움직이는 번호 제외(09-30 울타리 시험): 발끝이 처음 자리에서 박스 키 x f(최소 8px) 움직이기 전까지 규칙에 안 넣는다"""
    def run(tracked):
        first, moved, out = {}, set(), []
        for t, boxes in tracked:
            keep = []
            for b in boxes:
                pid, _c, x1, y1, x2, y2 = b
                foot = ((x1 + x2) / 2, y2)
                fx, fy = first.setdefault(pid, foot)
                if pid not in moved and ((foot[0] - fx) ** 2 + (foot[1] - fy) ** 2) ** 0.5 >= max(8.0, f * (y2 - y1)):
                    moved.add(pid)
                if pid in moved:
                    keep.append(b)
            out.append((t, keep))
        return out
    return run


def seam8(dets):
    """조각 정리, 경계 허용 8px. 09-30 C00_239_0001: 위 조각 아래 끝이 타일 경계 528 이 아니라 522 ~ 524 에서 끝나 2px 로는 거의 안 합쳐졌다"""
    return seam_fix(dets, tol=8.0)


def cut_out(tol=8.0, W=1280, H=720, grid=3, overlap=0.2, bottom_only=False):
    """타일 경계에 잘린 박스는 추적만 하고 진입 판정에서 뺀다(09-30 C00_057_0001: y=288 경계에 잘린 윗몸 조각은
    꼭짓점 4개가 구역 안인데 실제 발끝은 구역 밖 → 정답보다 10초 일찍 진입. C00_255_0001 다리 조각도 같은 꼴).
    잘림 = 박스 아래끝이 위 타일 끝(288 · 528) 근처, 위끝이 아래 타일 시작(192 · 432) 근처, 좌우도 같은 식(tol px)"""
    th, tw = H // grid, W // grid
    oy, ox = int(th * overlap), int(tw * overlap)
    yb = [((g + 1) * th - oy, (g + 1) * th + oy) for g in range(grid - 1)]
    xb = [((g + 1) * tw - ox, (g + 1) * tw + ox) for g in range(grid - 1)]
    near = lambda v, e: abs(v - e) <= tol

    def cut(x1, y1, x2, y2):
        if bottom_only:                                      # 발끝을 모르는 박스만(아래끝이 위 타일 끝에 잘림)
            return any(near(y2, hi) for _lo, hi in yb)
        return any(near(y2, hi) or near(y1, lo) for lo, hi in yb) or any(near(x2, hi) or near(x1, lo) for lo, hi in xb)

    def run(tracked):
        return [(t, [b for b in boxes if not cut(*b[2:])]) for t, boxes in tracked]
    return run


class CapTracker(K.Tracker):
    """판정기 Tracker 와 같고, 놓친 동안 늘어나는 중심 거리 한도만 2번 놓친 만큼으로 묶는다.
    판정기는 한도 = max(60, 0.8 x 박스 긴 변) x (1 + 놓친 횟수) 라 4.5초(9번) 놓치면 약 1,700px 까지 늘어
    화면 반대편에서 들어온 다른 사람이 옛 번호를 받는다(09-30 C00_239_0001: 둘째 사람이 첫 사람 번호를 받아 새 진입자로 안 셈)"""
    MISS_CAP = 2

    def update(self, dets):
        import math
        for t in self.tracks:
            t["miss"] += 1
        out, used = [], set()
        for conf, x1, y1, x2, y2 in sorted(dets, key=lambda d: -d[0]):
            box = (x1, y1, x2, y2)
            best, bi = self.iou_thr, None
            for i, t in enumerate(self.tracks):
                if i in used:
                    continue
                v = K.iou(box, t["box"])
                if v > best:
                    best, bi = v, i
            if bi is None:
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                dbest, di = 1e18, None
                for i, t in enumerate(self.tracks):
                    if i in used:
                        continue
                    tx1, ty1, tx2, ty2 = t["box"]
                    d = math.hypot(cx - (tx1 + tx2) / 2, cy - (ty1 + ty2) / 2)
                    lim = max(60.0, 0.8 * max(x2 - x1, y2 - y1)) * (1 + min(t["miss"], self.MISS_CAP))
                    if d < dbest and d <= lim:
                        dbest, di = d, i
                bi = di
            if bi is None:
                self.tracks.append({"id": self.next_id, "box": box, "miss": 0})
                used.add(len(self.tracks) - 1)
                out.append((self.next_id, round(conf, 3), *box))
                self.next_id += 1
            else:
                self.tracks[bi]["box"] = box; self.tracks[bi]["miss"] = 0; used.add(bi)
                out.append((self.tracks[bi]["id"], round(conf, 3), *box))
        self.tracks = [t for t in self.tracks if t["miss"] <= self.max_gap]
        return out


B_RULE = dict(corners=4, hold=1, gap=2)                     # 유예 규칙 B(09-30 연구개발 117편 최고 벌): 몸 전체 · 0.5초 · 끊김 1초
# id(폴더 이름, 영문) → 화면 이름 · 박스 후처리 · 번호 거르기 · 규칙 상수(판정기 cfg 를 덮음). 항목별
VARIANTS = {
    "intrusion": {
        "seam": dict(label="조각 정리", post=seam_fix),
        "contain": dict(label="겹침 제거", post=contain),
        "seamB": dict(label="조각 정리 + 규칙 B", post=seam_fix, rule=B_RULE),
        "seamBstill": dict(label="조각 정리 + 규칙 B + 정지 번호 제외", post=seam_fix, rule=B_RULE, track=still_out(1.0)),
        "seam8": dict(label="조각 정리(허용 8px)", post=seam8),
        "trk": dict(label="번호 거리 한도", tracker=CapTracker),
        "seam8trkfoot": dict(label="조각 정리(허용 8px) + 번호 거리 한도 + 발끝 잘린 박스 진입 제외", post=seam8, tracker=CapTracker, track=cut_out(bottom_only=True)),
    },
}
NONE = dict(label="없음(검산용)")


def label(ck):
    base, _, v = ck.partition("+")
    for item in VARIANTS.values():
        if v in item:
            return f"{base} + {item[v]['label']}"
    return ck


# ---------------------------------------------------------------- 계산
def _gts(item):
    return {p.stem: (K.read_alarms(p.with_suffix(".xml")) if p.with_suffix(".xml").is_file() else [])
            for p in RC.clips({v: k for k, v in RC.ITEM_OF.items()}[item])}


def rerun(item, clip, v, gts):
    """검수 캐시 한 편을 기술 v 로 다시 판정. 반환 = 원래 캐시와 같은 모양의 dict"""
    cfg = dict(K.ITEMS[item]); cfg.update(v.get("rule") or {})
    poly = [tuple(p) for p in clip["zone"]] if clip.get("zone") else None
    rule = K.IntrusionRule(poly, cfg["conf"], cfg["corners"], cfg["hold"], cfg["settle"], cfg["gap"])
    tr = (v.get("tracker") or K.Tracker)()
    tracked = []
    for t, boxes in clip["samples"]:
        dets = [[c, x1, y1, x2, y2] for _pid, c, x1, y1, x2, y2 in boxes]
        if v.get("post"):
            dets = v["post"](dets)
        tracked.append((t, tr.update([tuple(d) for d in dets])))
    if v.get("track"):
        tracked = v["track"](tracked)
    onset, samples, signal = None, [], []
    for t, boxes in tracked:
        if onset is None:
            onset = rule.feed(t, boxes)
        inside = [c for _pid, c, x1, y1, x2, y2 in boxes if K.entered((x1, y1, x2, y2), poly, cfg["corners"])]
        samples.append([t, [[int(p), c, a, b, x, y] for p, c, a, b, x, y in boxes]])
        signal.append([t, max(inside) if inside else 0.0])
    o = onset if onset is not None else rule.final()
    sa = None if o is None else RC._r(o + cfg["delay"], 2)
    g = gts.get(clip["clip"], [])
    out = dict(clip, samples=samples, signal=signal, alarm=sa, verdict=RC._verdict(K, g[0]["start_s"] if g else None, sa),
               conf=cfg["conf"], variant=v["label"])
    return out, (g, [{"start_s": sa, "desc": cfg["desc"]}] if sa is not None else [])


def build(exp, ck, item, vid, gts=None, write=True):
    v = NONE if vid == "none" else VARIANTS[item][vid]
    src = RC.cache_dir(exp, ck, item)
    base = json.loads((src / "summary.json").read_text(encoding="utf-8"))
    gts = gts if gts is not None else _gts(item)
    dst = RC.cache_dir(exp, f"{ck}+{vid}", item)
    rows, pairs, got = {}, [], {}
    for name in base["clips"]:
        clip = json.loads((src / (name + ".json")).read_text(encoding="utf-8"))
        r, pair = rerun(item, clip, v, gts)
        pairs.append(pair); got[name] = r
        rows[name] = {"alarm": r["alarm"], "gt": r["gt"], "verdict": r["verdict"]}
    s = K.score(pairs)
    summ = dict(base, ckpt=f"{ck}+{vid}", variant=v["label"], base=f"{exp}|{ck}", made=RC.now(), clips=rows,
                score={"정검": s["정상검출"], "미검": s["미검출"], "오검": s["오검출"], "점수": round(s["점수"], 2)})
    if write:
        dst.mkdir(parents=True, exist_ok=True)
        for name, r in got.items():
            (dst / (name + ".json")).write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp = dst / "summary.json.tmp"
        tmp.write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(dst / "summary.json")                    # summary 가 마지막 = 다 쓴 뒤에만 '끝남'
    return summ, base


def top(item, models):
    """상위 3개 = 작업 PC 공식 점수(없으면 검수 캐시 점수) 높은 순, 같으면 오검 적은 순. models = review_models 의 목록"""
    def key(m):
        s = m.get("official") or m.get("score") or {}
        return (s.get("점수", -1), -s.get("오검", 99))
    done = [m for m in models if m.get("done") and "+" not in m["ckpt"]]
    return sorted(done, key=key, reverse=True)[:TOP_N]


def is_fresh(exp, ck, item, vid):
    """기술 결과가 있고 원래 캐시(가중치 시각)와 맞나"""
    s = RC.cache_dir(exp, f"{ck}+{vid}", item) / "summary.json"
    b = RC.cache_dir(exp, ck, item) / "summary.json"
    if not (s.is_file() and b.is_file()):
        return False
    try:
        return json.loads(s.read_text(encoding="utf-8")).get("weights_mtime") == json.loads(b.read_text(encoding="utf-8")).get("weights_mtime")
    except Exception:
        return False


_LOCK = threading.Lock()


def compute_missing(item, tops):
    """화면 서버가 부른다. 상위 3개에 빠진 기술을 뒤에서 하나씩 계산(한 번에 한 줄기)"""
    todo = [(m["exp"], m["ckpt"], vid) for m in tops for vid in VARIANTS.get(item, {}) if not is_fresh(m["exp"], m["ckpt"], item, vid)]
    if not todo or not _LOCK.acquire(blocking=False):
        return todo

    def run():
        try:
            gts = _gts(item)
            for exp, ck, vid in todo:
                t0 = time.time()
                s, _ = build(exp, ck, item, vid, gts)
                print(f"[후처리] {exp} {ck}+{vid} {item} → {s['score']['점수']} ({time.time() - t0:.0f}초)", flush=True)
        except Exception as e:
            print("[후처리] 실패", e, flush=True)
        finally:
            _LOCK.release()
    threading.Thread(target=run, daemon=True).start()
    return todo


def check():
    """기술 없음으로 다시 돈 경보가 원래 캐시와 편마다 같아야 이 계산을 믿는다"""
    bad = n = diff_score = 0
    for item in VARIANTS:
        gts = _gts(item)
        for exp, m in RC.eligible():
            for ck in RC.CKPTS:
                if not (RC.cache_dir(exp, ck, item) / "summary.json").is_file():
                    continue
                s, base = build(exp, ck, item, "none", gts, write=False)
                for c, r in s["clips"].items():
                    n += 1
                    if r["alarm"] != base["clips"][c]["alarm"]:
                        bad += 1
                        print("  다름", exp, ck, c, r["alarm"], base["clips"][c]["alarm"])
                print(f"{exp} {ck} {item}: {s['score']['점수']} / 원래 {base['score']['점수']}")
                diff_score += s["score"] != base["score"]
    # ponytail: 캐시가 좌표 소수 1자리 · 신뢰도 3자리로 반올림돼 있어 문턱(0.45) 경계 · 번호 매칭이 드물게 뒤집힌다
    #   (09-30 검산 600편 중 10편, 점수는 20판 모두 같음). 편 단위 비교가 중요해지면 캐시를 반올림 없이 다시 만든다
    print(f"검산: {n}편 중 다름 {bad}({bad / max(n, 1):.1%}), 점수 다른 판 {diff_score}")
    assert diff_score == 0 and bad <= 0.02 * n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        check()

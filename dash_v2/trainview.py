# -*- coding: utf-8 -*-
"""학습 데이터 보기(2026-10-01): 실험이 실제로 학습에 쓴 셋 · 사진 · 박스를 눈으로 확인하고, 수상한 사진을 먼저 고른다.
읽기만 한다(라벨 · 목록을 고치지 않는다). 셋을 찾는 순서 · 사진 목록 규칙은 scripts/exp_queue.py 의 find_dataset · list_images 와 같게 둔다.
  실험 구성 = results/<실험>/meta.json(끝난 판) 또는 configs/queue_*.yaml(대기 · 학습 중) 의 base · base_frac · oversample · extras
  라벨 = 사진 경로의 마지막 /images/ 를 /labels/ 로, 확장자를 .txt 로(ultralytics 규칙). 심링크는 따라가지 않고 경로 그대로 바꾼다
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
G = HERE.parent
ROOTS = [G / "data/학습데이터", G / "data/원본데이터"]                     # exp_queue 의 TRAIN_DS · RAW_DS 순서
EXTRA_ROOTS = [Path("/NHNHOME/vms_r1280/data"), Path("/NHNHOME/vms_r960/data")]   # 줄인 사본만 있는 셋(보기용으로만 찾는다)
ALLOWED = [G / "data", *[r.parent for r in EXTRA_ROOTS]]              # 썸네일로 내줄 수 있는 곳
IMG_EXT = (".jpg", ".jpeg", ".png")
_NAME = re.compile(r"^[^/\\]+$")
_LOCK = threading.Lock()
_CACHE = {}                                                           # 셋 이름 → (서명, 행 목록). 최근 6개만
FLAGS = {                                                             # 화면 이름표(뜻이 이름표에 다 들어가게)
    "eval": "채점 영상 섞임", "out": "좌표 범위 밖", "cls": "클래스 번호 이상", "tiny": "아주 작은 박스",
    "huge": "화면 대부분 박스", "dup": "겹친 중복 박스", "many": "박스 30개 이상", "nolabel": "라벨 파일 없음",
}
STRONG = ("eval", "out", "cls", "dup", "nolabel")                       # '오류 의심'. 나머지(tiny · huge · many)는 '확인 권장'(공개셋에는 정상인 경우가 많다)
_TAIL = re.compile(r"_(fog|snow)[lmh]$")


def _eval_clips():
    """채점 영상(배포 검증 영상) 이름을 학습 항목별로. dash_meta.json 의 검수 항목 행 이름.
    학습하는 항목의 채점 영상만 '섞임' 으로 본다(사용자 09-24 · 09-26 확정): 사람 셋 = 침입 · 배회 채점편(쓰러짐 채점편 사본은 사람 학습 허용),
    방화 셋 = 방화 채점편 + 같은 카메라 146(C00_146_)"""
    try:
        m = json.loads((HERE / "dash_meta.json").read_text(encoding="utf-8")).get("items", {})
    except Exception:
        m = {}
    by = lambda ks: sorted({r["name"] for k in ks for r in (m.get(k) or {}).get("rows", []) if r.get("name")})
    return {"사람": by(("intrusion", "loiter")), "방화": by(("fire",)) + ["C00_146_"]}


def item_of(name):
    """셋 이름 → 학습 항목(사람 | 방화). configs/data_modules.yaml 의 item, 없으면 이름으로"""
    try:
        for m in (yaml.safe_load((G / "configs" / "data_modules.yaml").read_text(encoding="utf-8")) or {}).get("modules") or []:
            if m.get("name") == name and m.get("item") in ("사람", "방화"):
                return m["item"]
    except Exception:
        pass
    return "사람" if re.search(r"person|coco|hnfix|사람", name, re.I) else "방화"


EVAL = _eval_clips()


def set_dir(name):
    """셋 폴더(사진이 있는 첫 곳). 없으면 None"""
    if not _NAME.match(name or "") or ".." in name:
        return None
    for root in ROOTS + [r / sub for r in EXTRA_ROOTS for sub in ("학습데이터", "원본데이터")]:
        d = root / name
        if (d / "list.txt").is_file():                                 # 목록 모듈(mod_*) · 걸러 내기(flt_*) = 사진 폴더 없이 list.txt(계약 v4)
            return d
        for sub in ("images/train", "images"):
            if (d / sub).is_dir():
                return d
    return None


def here(p):
    """다른 서버(A · B) 저장소 뿌리로 적힌 절대 경로 → 이 서버 뿌리. 목록 파일은 만든 서버(A) 경로 그대로라 B 에선 이렇게 읽는다(10-03 사용자: B 는 A 와 늘 같게).
    '/data/' 부터는 두 서버가 같다. 이 서버 경로 · 줄인 사본(EXTRA_ROOTS) 경로는 그대로"""
    i = p.find("/data/")
    if i < 0 or p.startswith(str(G) + "/") or any(p.startswith(str(r) + "/") for r in EXTRA_ROOTS):
        return p
    return str(G) + p[i:]


def list_images(d):
    lt = d / "list.txt"
    if lt.is_file():                                                   # 목록 모듈 = 이미지 절대 경로 줄. 걸러 내기는 이름만이라 사진을 짚을 수 없어 빈 목록
        return [here(x) for x in (ln.strip() for ln in lt.read_text(encoding="utf-8").splitlines()) if x.startswith("/")]
    for sub in ("images/train", "images"):
        s = d / sub
        if s.is_dir():
            files = sorted(str(p) for p in s.iterdir() if p.suffix.lower() in IMG_EXT)
            if files:
                return files
    return []


def label_of(img):
    i = img.rfind("/images/")
    return (img[:i] + "/labels/" + img[i + 8:] if i >= 0 else img).rsplit(".", 1)[0] + ".txt"


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a[1] - a[3] / 2, a[2] - a[4] / 2, a[1] + a[3] / 2, a[2] + a[4] / 2
    bx1, by1, bx2, by2 = b[1] - b[3] / 2, b[2] - b[4] / 2, b[1] + b[3] / 2, b[2] + b[4] / 2
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    u = a[3] * a[4] + b[3] * b[4] - inter
    return inter / u if u > 0 else 0.0


def check(img, boxes, has_label, ncls, item="사람"):
    """수상한 점 목록(FLAGS 키). boxes = [[cls, cx, cy, w, h]] 정규화. item = 이 셋이 학습하는 항목(채점 영상 섞임은 그 항목 것만)"""
    f = []
    stem = _TAIL.sub("", Path(img).stem)
    if any(c in stem for c in EVAL[item]):
        f.append("eval")
    if not has_label:
        f.append("nolabel")
    if any(b[3] <= 0 or b[4] <= 0 or b[1] - b[3] / 2 < -0.01 or b[1] + b[3] / 2 > 1.01 or b[2] - b[4] / 2 < -0.01 or b[2] + b[4] / 2 > 1.01 for b in boxes):
        f.append("out")
    if any(int(b[0]) != b[0] or b[0] < 0 or b[0] >= ncls for b in boxes):
        f.append("cls")
    if any(0 < b[3] < 0.008 or 0 < b[4] < 0.008 for b in boxes):                 # 1280 기준 10px 미만
        f.append("tiny")
    if any(b[3] * b[4] > 0.85 for b in boxes):
        f.append("huge")
    if len(boxes) >= 30:
        f.append("many")
    elif any(boxes[i][0] == boxes[j][0] and _iou(boxes[i], boxes[j]) >= 0.6 for i in range(len(boxes)) for j in range(i + 1, len(boxes))):
        f.append("dup")
    return f


def _read(img, ncls, item):
    lp = Path(label_of(img))
    boxes, has = [], lp.is_file()
    if has:
        try:
            for ln in lp.read_text(encoding="utf-8", errors="replace").splitlines():
                w = ln.split()
                if len(w) >= 5:
                    boxes.append([float(x) for x in w[:5]])
        except Exception:
            pass
    return [img, boxes, check(img, boxes, has, ncls, item)]


def _sig(d, imgs):
    """셋 서명 = 폴더 · 장수 · labels mtime. 같으면 다시 세지 않는다"""
    return [str(d), len(imgs), (d / "labels").stat().st_mtime if (d / "labels").exists() else 0]


def _scan(d, imgs, name):
    item = item_of(name)
    ncls = _ncls(d, item)
    with ThreadPoolExecutor(32) as ex:                                 # 라벨 파일 수만 개를 Lustre 에서 읽는다
        return list(ex.map(lambda p: _read(p, ncls, item), imgs, chunksize=256))


def _count(R):
    counts = {k: 0 for k in FLAGS}
    sus = bg = 0
    for _, b, f in R:
        for k in f:
            counts[k] += 1
        sus += any(k in STRONG for k in f)
        bg += not b
    return counts, sus, bg


def _ncls(d, item):
    try:
        names = (yaml.safe_load((d / "data.yaml").read_text(encoding="utf-8")) or {}).get("names")
        if names:
            return len(names)
    except Exception:
        pass
    return 1 if item == "사람" else 2                                 # data.yaml 없는 목록 모듈(mod_*): 사람 = person 하나, 방화 = 불 · 연기


def rows(name):
    """셋 전체 행 [경로, 박스, 수상한 점]. 폴더가 그대로면 기억해 둔 것을 쓴다"""
    d = set_dir(name)
    if d is None:
        return None, None
    imgs = list_images(d)
    sig = _sig(d, imgs)
    with _LOCK:
        c = _CACHE.get(name)
        if c and c[0] == sig:
            return d, c[1]
    out = _scan(d, imgs, name)
    with _LOCK:
        _CACHE[name] = (sig, out)
        while len(_CACHE) > 6:
            _CACHE.pop(next(iter(_CACHE)))
    return d, out


def set_page(name, flag="", offset=0, limit=60):
    d, R = rows(name)
    if R is None:
        return {"error": f"이 서버에는 이 셋의 사진이 없습니다: {name}(학습셋은 서버 A 에만 있다)"}
    counts, sus, bg = _count(R)
    if flag == "sus":
        sel = [r for r in R if any(k in STRONG for k in r[2])]
    elif flag == "bg":
        sel = [r for r in R if not r[1]]
    elif flag in FLAGS:
        sel = [r for r in R if flag in r[2]]
    else:
        sel = R
    meta = {}
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"name": name, "dir": str(d.relative_to(G)) if G in d.parents else str(d), "total": len(R), "sel": len(sel),
            "sus": sus, "bg": bg, "counts": counts, "labels": FLAGS,
            "meta": {k: meta.get(k) for k in ("built", "mode", "source", "counts", "note", "bg_ratio") if meta.get(k) is not None},
            "items": [{"p": p, "boxes": b, "flags": f} for p, b, f in sel[offset:offset + limit]]}


def data_modules():
    """학습 데이터 모듈 목록 = configs/data_modules.yaml(계약 v4) 그대로. 목록만 있는 파일이면 {modules: [...]}"""
    d = yaml.safe_load((G / "configs/data_modules.yaml").read_text(encoding="utf-8")) or {}
    return {"modules": d} if isinstance(d, list) else d


# ---------- 모듈 요약(입력 데이터 탭 왼쪽 목록, 2026-10-02) ----------
# 첫 화면에서 모듈마다 라벨 파일을 다 읽으면 수십만 개(서버 A = Lustre)라, 요약을 디스크에 기억하고 백그라운드 스레드 하나가 차례로 센다.
# 기억 파일은 logs/ 아래(저장소 .gitignore 가 logs/ 를 무시한다)
SUM_FILE = G / "logs/dash/tv_summary.json"
_SUM = {"memo": None, "run": False, "at": 0.0}


def summary(name, old_sig=None):
    """셋 요약 {sig, total, sus, counts}. 서명이 old_sig 와 같으면 None(다시 안 셈). 셋이 이 서버에 없으면 {error}"""
    d = set_dir(name)
    if d is None:
        return {"error": f"이 서버에는 이 셋의 사진이 없습니다: {name}"}
    imgs = list_images(d)
    sig = _sig(d, imgs)
    if sig == old_sig:
        return None
    with _LOCK:
        c = _CACHE.get(name)
    R = c[1] if c and c[0] == sig else _scan(d, imgs, name)             # 화면에서 막 연 셋이면 읽어 둔 것을 쓴다(_CACHE 는 건드리지 않는다)
    counts, sus, _ = _count(R)
    return {"sig": sig, "total": len(R), "sus": sus, "counts": counts}


def _sum_run(names):
    try:
        for n in names:
            with _LOCK:
                old = (_SUM["memo"].get(n) or {}).get("sig")
            try:
                s = summary(n, old)
            except Exception as ex:
                s = {"error": f"{type(ex).__name__}: {ex}"}
            if s is None:
                continue
            with _LOCK:
                _SUM["memo"][n] = s
                body = json.dumps(_SUM["memo"], ensure_ascii=False)
            SUM_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SUM_FILE.with_suffix(".json.tmp")
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(SUM_FILE)
    finally:
        with _LOCK:
            _SUM["run"], _SUM["at"] = False, time.time()


def summaries(recheck=600):
    """모듈(걸러 내기 flt_* 빼고)마다 {name, total, sus, counts} 또는 {name, error}. 아직 안 센 것은 pending.
    없는 것 · recheck 초가 지난 것은 백그라운드 스레드 하나가 서명을 보고 바뀐 것만 다시 센다"""
    names = [m["name"] for m in data_modules().get("modules") or [] if m.get("name") and m.get("kind") != "filter"]
    with _LOCK:
        if _SUM["memo"] is None:
            try:
                _SUM["memo"] = json.loads(SUM_FILE.read_text(encoding="utf-8"))
            except Exception:
                _SUM["memo"] = {}
        memo = _SUM["memo"]
        mods = [dict({k: v for k, v in memo[n].items() if k != "sig"}, name=n) for n in names if n in memo]
        pending = [n for n in names if n not in memo]
        if not _SUM["run"] and (pending or time.time() - _SUM["at"] > recheck):
            _SUM["run"] = True
            threading.Thread(target=_sum_run, args=(names,), daemon=True).start()
    return {"mods": mods, "pending": pending}


def allowed(path):
    """허용된 폴더(ALLOWED) 안의 사진 파일이면 실제 경로, 아니면 None. 썸네일 · 학습 제외 저장이 같이 쓴다"""
    p = Path(str(path))
    try:
        rp = p.resolve()
    except Exception:
        return None
    if p.suffix.lower() not in IMG_EXT or not rp.is_file() or not any(a in rp.parents for a in ALLOWED + [a.resolve() for a in ALLOWED]):
        return None
    return rp


def _queue_entries():
    out = {}
    for q in sorted((G / "configs").glob("queue*.yaml")):
        try:
            d = yaml.safe_load(q.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        dft = d.get("defaults") or {}
        for e in d.get("experiments") or []:
            if e.get("name"):
                cp = e.get("compose")                                  # 조합 판(계약 v4)은 base · extras · oversample 대신 compose
                out[e["name"]] = {"compose": cp, "base": None if cp else e.get("base", dft.get("base", "aihub71751_48k")), "base_frac": e.get("base_frac", dft.get("base_frac", 1.0)),
                                  "oversample": dict(dft.get("oversample") or {}, **(e.get("oversample") or {})), "extras": list(e.get("extras") or []),
                                  "item": e.get("item", dft.get("item")), "phase": e.get("phase"), "queue": q.name}
    return out


def exps(limit=60):
    """실험 목록(최근 먼저). 셋 구성 = 베이스 · 반복 셋 · 추가 셋"""
    import time
    Q, out, seen = _queue_entries(), [], set()
    for f in (G / "results").glob("*/meta.json"):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not (m.get("base") or m.get("compose")):
            continue
        out.append({"exp": f.parent.name, "item": m.get("item"), "phase": m.get("phase"), "status": m.get("status"), "when": m.get("started") or "",
                    "compose": m.get("compose"), "base": m.get("base"), "base_frac": m.get("base_frac", 1.0), "oversample": m.get("oversample") or {}, "extras": m.get("extras") or [],
                    "n_train": m.get("n_train")})
        seen.add(f.parent.name)
    fresh = {q.name for q in (G / "configs").glob("queue*.yaml") if time.time() - q.stat().st_mtime < 2 * 86400}
    for x, e in Q.items():                                             # 아직 meta 가 없는 판: 지금 학습 중(_exp 목록 있음) 또는 2일 안에 고친 큐의 대기 판. 옛 큐의 취소된 판은 뺀다
        if x in seen:
            continue
        tl = G / "_exp" / x / "train.txt"
        busy = tl.is_file() and time.time() - tl.stat().st_mtime < 3 * 86400        # 오래된 _exp 찌꺼기는 학습 중으로 보지 않는다
        if busy or e["queue"] in fresh:
            out.append(dict(e, exp=x, status="학습 중" if busy else "대기", when="9999" if busy else "9998", n_train=None))
    out.sort(key=lambda r: r["when"], reverse=True)
    for r in out[:limit]:
        cp = r.get("compose")
        if cp:                                                         # 조합 판: 쓴 모듈(반복 배율) · use 밖 반복 · 걸러 내기 · 배경 우선 목록
            use, rp = cp.get("use") or [], cp.get("repeat") or {}
            sets = [{"name": s, "role": "모듈", "k": int(rp.get(s, 1))} for s in use]
            sets += [{"name": s, "role": "반복", "k": int(k)} for s, k in rp.items() if s not in use]
            sets += [{"name": s, "role": "빼기", "k": 1} for s in cp.get("exclude") or []]
            sets += [{"name": s, "role": "배경 우선", "k": 1} for s in (cp.get("background") or {}).get("prefer") or []]
        else:
            sets = [{"name": r["base"], "role": "베이스", "k": 1, "frac": r["base_frac"]}]
            sets += [{"name": s, "role": "반복", "k": int(k)} for s, k in r["oversample"].items()]
            sets += [{"name": s, "role": "추가", "k": 1} for s in r["extras"]]
        r["sets"] = sets
    return {"exps": out[:limit], "eval_clips": sum(len(v) for v in EVAL.values())}


def thumb(path, w=320):
    """사진 축소본 JPEG. 허용된 폴더 밖이면 None"""
    rp = allowed(path)
    if rp is None:
        return None
    from PIL import Image
    im = Image.open(rp)
    im.thumbnail((w, w * 10))
    b = BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=80)
    return b.getvalue()


if __name__ == "__main__":
    a = [0, 0.5, 0.5, 0.2, 0.2]
    assert check("x/images/a.jpg", [a, list(a)], True, 1) == ["dup"]
    assert "out" in check("x/images/a.jpg", [[0, 0.95, 0.5, 0.2, 0.2]], True, 1)
    assert "cls" in check("x/images/a.jpg", [[1, 0.5, 0.5, 0.1, 0.1]], True, 1)
    assert check("x/images/a.jpg", [], False, 1) == ["nolabel"]
    assert label_of("/a/images/train/b.jpg") == "/a/labels/train/b.txt"
    if EVAL["사람"]:                                                   # 서버(dash_meta.json 있는 곳)에서만
        assert "eval" in check("x/images/C00_005_0001_00010.jpg", [], True, 1, "사람")            # 침입 채점편 = 섞임
        assert "eval" not in check("x/images/fall_C00_146_0004_00010.jpg", [], True, 1, "사람")   # 쓰러짐 채점편 사본 = 사람 학습 허용
        assert "eval" in check("x/images/C00_146_0001_00010.jpg", [], True, 2, "방화")            # 방화 = 같은 카메라 146 도
    assert item_of("mod_person_coco_pos_20260927") == "사람" and item_of("fasdd_yolo") == "방화"
    print("ok", {k: len(v) for k, v in EVAL.items()}, "eval clips")

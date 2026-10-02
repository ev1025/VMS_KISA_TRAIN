# -*- coding: utf-8 -*-
"""KISA 검수 대시보드 서버(서버에서 실행, ssh -L 8890 으로 로컬 브라우저 접속).

라벨 저장소 셋(표시·학습 우선순위 순):
  손라벨   data/학습데이터/손라벨/{person,fire}_labels.json   /api/savelabel · /api/labels · /api/clearlabels
  SAM 전파 data/학습데이터/자동라벨/sam2/<stem>.json         /api/sam2_propagate_start(큐) · sam2_jobs · sam2_cancel · sam2_label · sam2_drop · sam2_drop_obj · sam2_clear · sam2frames
  (DINO 자동라벨은 2026-09-11 걷어냈다. 의사라벨을 쓰지 않기로 했다.) 프레임 찾기·초안용)
  정답     data/학습데이터/정답라벨/<stem>.json               /api/gtlabel (읽기 전용)
손라벨 박스가 있는 프레임은 SAM 저장소에서 빠진다(savelabel 이 빼고, 전파 저장이 건너뛴다).
SAM: /api/sam2_mask(한 프레임 점·박스 → 마스크), 전파 방식 PROP_DEFAULT_MODE(separate·joint)
데이터 확인: /api/sources · raw · clips · clipconds · clipinfo · frameat · warmframes · dsimg · dslabel · rawlabel · vid
입력 데이터: /api/data_modules · tv_summary · tv_set · tv_thumb · train_exclude(GET · POST, data/학습데이터/손라벨/train_exclude.json)
           · train_fix(GET · POST, data/학습데이터/손라벨/train_label_fix.json = 지울 박스 기록. 모듈 라벨 파일은 고치지 않는다)
결과: /api/meta · dataset · results · queue
"""
import json, os, re, shutil, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
# 데이터 루트 = 이 파일의 상위 폴더(= .../vms). 전에는 general_yolo 심링크를 하드코딩했는데
# 그 심링크가 지워지자 라벨·영상·프레임이 전부 404 가 됐다. 자기 위치 기준으로 잡으면 그런 일이 없다.
G = HERE.parent
# 영상·이미지를 내보낼 때 "이 경계 안의 파일만" 확인하는 기준. 심링크가 vms/data 로 나가도 허용한다.
# 다른 장비에 올려 돌릴 때는 VMS_WS 로 덮어쓴다. 기본값은 예전 동작 그대로다.
WS = Path(os.environ.get("VMS_WS") or G.parent)   # 저장소 바로 위 폴더. 서버 A 는 예전과 같은 경로, 사본 서버(B 등)는 그 서버 작업 폴더(2026-09-29)
RAW = G / "data/원본데이터"        # 라벨 대상 영상이 카테고리 폴더로 들어 있는 곳
PORT = 8890

_CI = {}          # 클립별 fps·프레임수 캐시. 영상을 열어봐야 아는 값이라 한 번만 읽는다
_SAVE_LOCK = threading.Lock()   # savelabel 은 read-modify-write. ThreadingHTTPServer 라 동시 저장 시 한쪽이 사라지는 걸 막는다


def _backup_labels(fl):
    """그날 첫 저장 전에 손라벨 JSON 스냅샷을 _backup/<이름>.<YYYYMMDD>.json 으로 남긴다(실수 복구용)."""
    try:
        if not fl.exists():
            return
        b = fl.parent / "_backup" / f"{fl.stem}.{time.strftime('%Y%m%d')}.json"
        if not b.exists():
            b.parent.mkdir(exist_ok=True); shutil.copyfile(fl, b)
    except Exception:
        pass
_CLIPS = {}       # 카테고리별 영상 목록 캐시


import gt_adapters as GTA              # 데이터 규격 계층(원본 정답 형식별 어댑터 + datasets.yaml)
DATASETS = GTA.Datasets(G / "configs/datasets.yaml", RAW)   # 카테고리 설정 단일 기준(mode·media·gt·classes·use)


def cat_of(rel_or_clip):
    """'data/원본데이터/<cat>/...' · '<cat>/...' · 'img:data/원본데이터/<cat>/...' 어느 꼴이든 카테고리 이름."""
    s = str(rel_or_clip).replace("\\", "/")
    if s.startswith("img:"):
        s = s[4:]
    parts = [q for q in s.split("/") if q]
    if len(parts) >= 3 and parts[0] == "data" and parts[1] == "원본데이터":
        return parts[2]
    return parts[0] if parts else ""


def label_file(kind):
    """손라벨 파일. person = 사람 영상, image = 이미지 데이터셋(정지 이미지, 클립 대신 'img:<상대경로>'), 그 외 = 화재 영상."""
    fn = "person_labels.json" if kind == "person" else ("image_labels.json" if kind == "image" else "fire_labels.json")
    return data_path("data/학습데이터/손라벨/" + fn, fn)


def train_exclude_file():
    """학습 제외 목록(입력 데이터 탭 X). 손라벨 파일들 옆. ML 이 name(이미지 파일 이름)으로 걸러 내기를 만든다"""
    return data_path("data/학습데이터/손라벨/train_exclude.json", "train_exclude.json")


def _train_item(b):
    """학습 제외 · 라벨 고침 한 줄의 공통 칸 검사 → (set, path, on, 공통 칸). 넣을 때만 셋 · 경로를 본다(빼기는 목록에서 지우기만 해서 쓰는 값이 없다)"""
    import trainview as _TV
    from datetime import datetime, timedelta, timezone
    st, path, on = str(b.get("set") or ""), str(b.get("path") or ""), b.get("on", True) is not False
    if on and _TV.set_dir(st) is None:
        raise ValueError(f"모르는 셋: {st}")
    if on and _TV.allowed(path) is None:
        raise ValueError(f"허용된 폴더 밖이거나 사진이 아님: {path}")
    why = [str(x)[:60] for x in b.get("why") or [] if x][:10] if isinstance(b.get("why"), list) else []
    return st, path, on, {"set": st, "path": path, "name": Path(path).name, "why": why, "by": str(b.get("by") or "사용자")[:40],
                          "at": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")}


def _train_list_edit(fl, same, item):
    """손라벨 옆 목록 파일 {"items": [...]} 고치기: same(줄) 인 줄을 빼고 item 이 있으면 넣는다. 손라벨 저장과 같은 잠금 · 그날 첫 저장 전 백업"""
    with _SAVE_LOCK:
        _backup_labels(fl)
        d = read_json(fl, {})
        items = [x for x in (d.get("items") if isinstance(d, dict) else None) or [] if not same(x)]
        if item:
            items.append(item)
        write_json(fl, {"items": items})
    return {"ok": True, "items": items}


def train_exclude_write(b):
    """{set, path, why, on} 하나를 넣거나(on 참) 뺀다(on=false). 형식 {"items": [{set, path, name, why, by, at}]}, 경로마다 한 줄"""
    st, path, on, item = _train_item(b)
    return _train_list_edit(train_exclude_file(), lambda x: x.get("path") == path, item if on else None)


def train_fix_file():
    """라벨 고침 기록(입력 데이터 탭 '박스 지우기'). 손라벨 파일들 옆. 이 박스를 학습 라벨에서 빼 달라는 기록이고, 모듈 라벨 파일은 고치지 않는다(ML 규칙: 모듈 불변)"""
    return data_path("data/학습데이터/손라벨/train_label_fix.json", "train_label_fix.json")


def train_fix_write(b):
    """{set, path, box: [cls, cx, cy, w, h], why, on} 하나를 넣거나(on 참) 뺀다(on=false). 형식 {"items": [{set, path, name, box, why, by, at}]}.
    box = 라벨 파일 줄 값 그대로, 같은 박스 = 같은 path + box(소수 5자리)면 한 줄"""
    import math
    box = b.get("box")
    if not (isinstance(box, list) and len(box) == 5 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in box)):
        raise ValueError("box 는 숫자 5개 [cls, cx, cy, w, h]")
    st, path, on, item = _train_item(b)
    rk = lambda bx: [round(float(v), 5) for v in bx] if isinstance(bx, list) and len(bx) == 5 else None
    key = rk(box)
    return _train_list_edit(train_fix_file(), lambda x: x.get("path") == path and rk(x.get("box")) == key, dict(item, box=box) if on else None)


def clip_state_file():
    """클립별 상태(표시·전파 구간). 손라벨 파일들 옆에 둔다 → push 가 폴더째 보내 준다."""
    return data_path("data/학습데이터/손라벨/clip_state.json", "clip_state.json")


def read_json(path, default):
    try:
        path = Path(path)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write_json(path, obj):
    """임시 파일에 쓰고 바꿔 넣는다(쓰다 죽어도 반쪽 파일이 남지 않는다). 프로세스마다 임시 이름이 다르다.
    원본데이터(RAW) 아래에는 절대 쓰지 않는다: 우리가 만든 라벨은 전부 data/학습데이터 아래 별도 저장소로 간다."""
    path = Path(path)
    try:
        if RAW.resolve() in path.resolve().parents:
            raise PermissionError(f"원본데이터 아래에는 쓰지 않는다: {path}")
    except PermissionError:
        raise
    except Exception:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8"); tmp.replace(path)


def tkey(t):
    """저장소 프레임 키. 0.5초 격자(사람 2FPS)로 맞춘 "190.5" 꼴. 화재(1초)도 같은 격자 위에 있다."""
    return f"{round(float(t) * 2) / 2:.1f}"


def nms_keep(dets, iou_th=0.4, cover_th=0.9):
    """dets = [(score, x1, y1, x2, y2, ...)] 점수순으로 겹침(IoU)·포함(한쪽이 90% 이상 덮임) 중복을 뺀다."""
    def _ov(a, b):
        ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1]); ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        sa = (a[2] - a[0]) * (a[3] - a[1]); sb = (b[2] - b[0]) * (b[3] - b[1]); ua = sa + sb - inter
        return (inter / ua if ua > 0 else 0.0, max(inter / sa if sa > 0 else 0.0, inter / sb if sb > 0 else 0.0))
    keep = []
    for d in sorted(dets, key=lambda x: -x[0]):
        if all((lambda v: v[0] < iou_th and v[1] < cover_th)(_ov(d[1:5], k[1:5])) for k in keep):
            keep.append(d)
    return keep


def data_path(*cands):
    """후보 경로 중 실제로 있는 것을 쓴다. 폴더 재구성(labelfull → data/학습데이터/손라벨/full,
    fire_labels.json → data/학습데이터/손라벨/fire_labels.json)에도 안 깨지게 하려는 것."""
    for c in cands:
        q = G / c
        if q.exists():
            return q
    return G / cands[0]


_COCO = {}   # annotations json 경로 -> {파일명: YOLO 라벨 문자열}. 한 번만 파싱해 캐시


def raw_sibling_label(rel):
    """이미지와 라벨이 다른 트리에 있는 원본에서 YOLO txt 를 찾는다.
    예: open_coco/train2017/x.jpg -> open_coco/coco/labels/train2017/x.txt
    카테고리 루트 아래 labels/<이미지 상위폴더>/<같은 이름>.txt 를 깊이 3까지 본다(glob 이라 훑지 않는다)."""
    _r = str(rel).replace("\\", "/")
    if "/images/" in _r:   # YOLO 표준: .../images/x.jpg <-> .../labels/x.txt (같은 레벨)
        cand = G / (_r.rsplit("/images/", 1)[0] + "/labels/" + Path(_r).stem + ".txt")
        if cand.is_file():
            return cand
    parts = _r.split("/")
    if len(parts) < 4 or parts[0] != "data" or parts[1] != "원본데이터":
        return None
    root = G / parts[0] / parts[1] / parts[2]
    stem, parent = Path(rel).stem, parts[-2]
    for pat in (f"labels/{parent}/{stem}.txt", f"*/labels/{parent}/{stem}.txt",
                f"*/*/labels/{parent}/{stem}.txt", f"labels/{stem}.txt", f"*/labels/{stem}.txt"):
        for q in root.glob(pat):
            if q.is_file():
                return q
    return None


def coco_labels(rel):
    """원본 COCO annotations(images/<split>/ + annotations/<split>.json)에서 그 이미지의 박스를
       YOLO(cls cx cy w h, 정규화) 문자열로 돌려준다. fasdd 등 test 스플릿까지 표시하려는 것."""
    m = re.match(r"(.*)/images/(train|val|test)/([^/]+)$", rel)
    if not m:
        return None
    base, split, fname = m.groups()
    jp = G / base / "annotations" / (split + ".json")
    if not jp.exists():
        return None
    key = str(jp)
    if key not in _COCO:
        idx = {}
        try:
            d = json.load(open(jp, encoding="utf-8"))
            info = {im["id"]: (im["file_name"], im["width"], im["height"]) for im in d.get("images", [])}
            lines = {}
            for a in d.get("annotations", []):
                it = info.get(a["image_id"])
                if not it:
                    continue
                fn, W, Hh = it
                x, y, w, h = a["bbox"]
                lines.setdefault(fn, []).append(
                    "%d %.6f %.6f %.6f %.6f" % (a["category_id"], (x + w / 2) / W, (y + h / 2) / Hh, w / W, h / Hh))
            idx = {fn: chr(10).join(v) for fn, v in lines.items()}
        except Exception:
            idx = {}
        _COCO[key] = idx
    return _COCO[key].get(fname, "")


def under_raw(rel, ext=""):
    """원본데이터 기준 상대경로를 안전하게 실경로로. 폴더 밖을 가리키면 None."""
    if not rel:
        return None
    rel = str(rel).replace("\\", "/")
    if ".." in rel.split("/"):
        return None
    p = RAW / (rel + ext)
    try:
        root, rp = RAW.resolve(), p.resolve()
    except OSError:
        return None
    return p if root == rp or root in rp.parents else None


def clips_of(cat):
    """카테고리 폴더 아래 mp4 전부(하위 폴더 포함). 원본데이터 기준 상대경로, 확장자 없음."""
    if cat in _CLIPS:
        return _CLIPS[cat]
    base = under_raw(cat)
    if base is None or not base.is_dir():
        return []
    rels = sorted(str(p.relative_to(RAW).with_suffix("")).replace("\\", "/")
                  for p in base.rglob("*.mp4"))
    _CLIPS[cat] = rels
    return rels


CACHE_DIR = HERE / "_cache"        # 폴더 스캔 결과를 디스크에 둔다(재시작해도 16초 스캔을 다시 안 함)
_SOURCES = None


def _cache_read(key):
    f = CACHE_DIR / (key + ".json")
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:
        return None


def _cache_write(key, obj):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        tmp = CACHE_DIR / (key + ".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8"); tmp.replace(CACHE_DIR / (key + ".json"))
    except Exception:
        pass


def clear_caches():
    """데이터 폴더를 옮기거나 이름을 바꾼 뒤 호출(대시보드 '캐시 새로고침' 버튼). 재시작 불필요."""
    global _SOURCES
    _SOURCES = None; _RAW.clear(); _CLIPS.clear(); _CI.clear(); _CONDS.clear()
    for f in CACHE_DIR.glob("*.json"):                # 폴더 스캔 결과만. 뽑아 둔 프레임(frames/)은 그대로
        try: f.unlink()
        except Exception: pass


def sources():
    """카테고리(원본데이터 1단계 폴더) 목록. count = 영상 편수(0 이면 이미지만 있는 폴더).
    첫 계산이 16초(전 카테고리 os.walk)라 메모리+디스크에 캐시한다."""
    global _SOURCES
    if _SOURCES is not None:
        return _SOURCES
    disk = _cache_read("sources")
    if disk is not None:
        _SOURCES = disk; return _SOURCES
    out = []
    if not RAW.is_dir():
        return out
    for d in sorted((p for p in RAW.iterdir() if p.is_dir()), key=lambda q: (1 if "flir" in q.name.lower() else 0, q.name)):
        out.append({"key": d.name, "count": len(clips_of(d.name))})
    _SOURCES = out; _cache_write("sources", out)
    return out


IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_RAW = {}          # 카테고리별 파일 목록 캐시(폴더를 한 번만 훑는다)


def raw_items(cat, limit=600):
    """카테고리 안의 이미지·영상 목록. 경로는 vms 기준 상대경로(=/dsimg, /vid 주소에 그대로 쓴다).
    수만 장이면 고르게 샘플만 준다(목록이 목적이 아니라 눈으로 확인하는 게 목적)."""
    if cat in _RAW:
        got = _RAW[cat]
    elif _cache_read("raw_" + cat) is not None:
        got = _RAW[cat] = _cache_read("raw_" + cat)
    else:
        base = under_raw(cat)
        if base is None or not base.is_dir():
            return None
        imgs, vids = [], []
        root_len = len(str(G)) + 1
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMG_EXT:
                    _rel = os.path.join(dirpath, fn)[root_len:].replace("\\", "/")
                    if "infrared" in _rel.lower() or "thermal" in _rel.lower():
                        continue   # 적외선/열화상은 데이터확인 브라우징에서 제외(가시광/RGB만)
                    imgs.append(_rel)
                elif ext == ".mp4":
                    vids.append(os.path.join(dirpath, fn)[root_len:].replace("\\", "/"))
        imgs.sort(); vids.sort()
        got = _RAW[cat] = {"images": imgs, "videos": vids}
        _cache_write("raw_" + cat, got)

    def samp(a):
        if len(a) <= limit:
            return a
        step = len(a) / limit
        return [a[int(i * step)] for i in range(limit)]

    # 영상은 자르지 않는다: 조건 필터(야간·설경)로 골라 라벨하는데 잘리면 대상이 사라진다
    return {"cat": cat, "img_total": len(got["images"]), "vid_total": len(got["videos"]),
            "images": samp(got["images"]), "videos": got["videos"]}


def fire_spans(clip, fps=30.0):
    """클립 옆 정답 파일에서 이벤트 구간을 읽는다. [{"start": 초, "dur": 초, "kind": 종류}, ...]
    - KISA XML: StartTime(발생 시각) + AlarmDuration(경보 인정 구간)
    - AI허브 JSON: annotations.event_frame[[시작프레임, 끝프레임]] → fps 로 초 변환
    라벨할 초를 여기서 찾는다."""
    xml = under_raw(clip, ".xml")
    if xml is None or not xml.exists():
        return json_spans(clip, fps)      # XML 이 없으면 AI허브 JSON 을 본다
    def secs(txt):
        parts = [int(x) for x in str(txt).strip().split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    import xml.etree.ElementTree as ET
    out = []
    try:
        for al in ET.parse(xml).getroot().iter("Alarm"):
            st = al.findtext("StartTime")
            if not st:
                continue
            out.append({"start": secs(st), "dur": secs(al.findtext("AlarmDuration") or "0:0:0"),
                        "kind": (al.findtext("AlarmDescription") or "").strip()})
    except Exception:
        return []      # XML 이 깨져도 라벨 화면은 돌아야 한다
    return out


def json_spans(clip, fps=30.0):
    """AI허브 라벨(JSON) 의 이벤트 구간. 침입·쓰러짐 영상이 이 형식이다."""
    js = under_raw(clip, ".json")
    if js is None or not js.exists():
        return []
    try:
        d = json.load(open(js, encoding="utf-8"))
        a = d.get("annotations") or {}
        f = float(fps) or 30.0
        out = []
        for fr in (a.get("event_frame") or []):
            if not isinstance(fr, (list, tuple)) or not fr:
                continue
            s0 = float(fr[0]) / f
            e0 = float(fr[1]) / f if len(fr) > 1 else s0
            out.append({"start": int(round(s0)), "dur": max(int(round(e0 - s0)), 0),
                        "kind": a.get("event_class") or "event",
                        "note": a.get("event_caption") or ""})
        return out
    except Exception:
        return []      # 라벨이 깨져도 라벨 생성 화면은 돌아야 한다


# ---------- 실험별 박스 덤프(영상 검수에서 모델 예측 박스를 영상 위에 겹쳐 보기) ----------
_BOXJOBS = {}                      # (실험, 클립) → "run" | "done" | "err:사유"
_BOXDIR = G / "dumps/fire_box"     # <실험>/<클립>.jsonl
BOX_TOP_SCORE = 3                 # 검수 탭 모델 목록: 갈래별 점수 상위 몇 개(순위는 scripts/model_rank.py)
BOX_TOP_RECENT = 5                # 〃 최근 학습 몇 개(meta.json 의 ended/started 순). 배포 가중치는 항상 (2026-09-26 사용자 요청)


# 시험 판정(VMS_KISA tools/kisa_items.py ITEMS["fire"] model·model2)과 같은 두 벌. 표본마다 두 모델 중 높은 값을 쓰므로 박스도 합쳐 본다
BOX_ENS = {"ens:fire": ("deploy:fire_fog.pt", "deploy:fire_small.pt")}


def _merge_rows(parts):
    """같은 영상·같은 간격 덤프 여러 개를 표본 시각별로 합친다(박스는 이어 붙임, 겹침은 화면 nms 가 지운다)."""
    by = {}
    for rows in parts:
        for r in rows or []:
            by.setdefault(r["t"], []).extend(r.get("boxes") or [])
    return [{"t": t, "boxes": b} for t, b in sorted(by.items())]


def box_state(exp, clip):
    """덤프 작업 상태. 앙상블은 두 벌의 상태를 합친다(하나라도 실패면 실패, 하나라도 도는 중이면 도는 중)."""
    if exp in BOX_ENS:
        sts = [box_state(m, clip) for m in BOX_ENS[exp]]
        for s in sts:
            if str(s).startswith("err"):
                return s
        return "run" if "run" in sts else ("none" if "none" in sts else "done")
    return _BOXJOBS.get((exp, clip), "none")


def box_models():
    """학습 가중치가 남아 있는 실험 목록 + 배포 중인 가중치. 고를 때 참고하도록 채점셋 mAP50 을 같이 싣는다."""
    out = []
    try:                                   # 배포 가중치(model/*.pt)는 results/ 에 없어 따로 넣는다
        import sys as _s
        if str(G / "scripts") not in _s.path:
            _s.path.insert(0, str(G / "scripts"))
        from model_rank import deployed as _dep
        for exp_, kind_, _key, _why in _dep():
            if kind_ == "fire" and exp_ not in BOX_ENS["ens:fire"]:
                continue                      # 지금 시험 설정에 없는 옛 방화 배포본(fire_snowfull 등)은 뺀다
            out.append({"exp": exp_, "model": "배포", "item": "방화" if kind_ == "fire" else "사람",
                        "kind": kind_, "map50": None, "f1": None})
        out.append({"exp": "ens:fire", "model": "배포", "item": "방화", "kind": "fire", "map50": None, "f1": None,
                    "why_fixed": "시험 판정 그대로: fire_fog + fire_small 박스 합침"})
    except Exception:
        pass
    rd = G / "results"
    if not rd.is_dir():
        return out
    for md in rd.glob("*/meta.json"):
        try:
            m = json.loads(md.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        pt = m.get("best_pt")
        if not pt or not Path(pt).is_file():
            continue
        if any(k in json.dumps([m.get("base"), m.get("oversample"), m.get("extras")], ensure_ascii=False) for k in ("human_fire", "evalset_fire")):
            continue                              # 누수 판(채점편 프레임으로 학습)은 목록에서 뺀다(2026-09-26)
        exp = md.parent.name
        em = {}
        ej = md.parent / "eval_map.json"          # 채점셋 mAP 는 별도 파일에 있다
        if ej.is_file():
            try:
                em = json.loads(ej.read_text(encoding="utf-8")) or {}
            except Exception:
                em = {}
        f1 = None
        st = md.parent / "score.txt"              # F1 = 규칙 스윕 중 최고값
        if st.is_file():
            try:
                for ln in st.read_text(encoding="utf-8").splitlines():
                    mm = re.search(r"→\s*([0-9]+\.[0-9]+)", ln)
                    if mm:
                        v = float(mm.group(1))
                        if f1 is None or v > f1:
                            f1 = v
            except Exception:
                pass
        item = m.get("item", "방화")
        # 화면에서 클립과 짝이 맞는 모델만 보여주려고 두 갈래로 정리한다.
        # item 은 방화 / 사람 / 침입 / 배회 / 쓰러짐 이 섞여 들어온다(큐 작성 시점마다 달랐다).
        out.append({"exp": exp, "model": m.get("model"), "item": item,
                    "kind": "fire" if item == "방화" else "person",
                    "map50": em.get("map50"), "f1": f1, "started": m.get("ended") or m.get("started")})
    # 순위는 scripts/model_rank.py 한 곳에서만 정한다(백필 순서와 화면 순서가 갈라지지 않게).
    try:
        import sys as _sys
        if str(G / "scripts") not in _sys.path:
            _sys.path.insert(0, str(G / "scripts"))
        from model_rank import rank as _rank, DEPLOY as _DEPLOY
        order, why = {}, {}
        for i, (exp_, kind_, key_, why_) in enumerate(_rank()):
            order[exp_] = i
            why[exp_] = why_
        for d in out:
            d["why"] = d.get("why_fixed") or why.get(d["exp"])
            d["deploy"] = _DEPLOY.get(d["exp"])
        out.sort(key=lambda d: (d["exp"] != "ens:fire", order.get(d["exp"], 10 ** 6)))   # 앙상블을 맨 위에
    except Exception:                    # 순위를 못 구하면 예전처럼 mAP 순
        out.sort(key=lambda d: (d["map50"] is None, -(d["map50"] or 0)))

    # 갈래별로 배포 가중치 + 점수 상위 BOX_TOP_SCORE + 최근 학습 BOX_TOP_RECENT 만. 목록이 길면 고르기만 어렵다(2026-09-26)
    top = []
    for k in ("fire", "person"):
        ds = [d for d in out if d["kind"] == k]
        dep = [d for d in ds if d["model"] == "배포"]
        rest = [d for d in ds if d["model"] != "배포"]                       # 이미 model_rank 순
        best = rest[:BOX_TOP_SCORE]
        bestn = {d["exp"] for d in best}
        recent = sorted((d for d in rest if d["exp"] not in bestn and d.get("started")),
                        key=lambda d: d["started"], reverse=True)[:BOX_TOP_RECENT]
        for d in dep:
            d["tag"] = "배포 앙상블" if d["exp"] in BOX_ENS else "배포"
        for i, d in enumerate(best):
            d["tag"] = "점수 %d위" % (i + 1)
        for d in recent:
            d["tag"] = "최근"
        top += dep + best + recent
    return top


def box_dump_path(exp, clip):
    return _BOXDIR / exp / (clip + ".jsonl")


def _read_jsonl(f):
    rows = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass
    return rows


def box_dump_read(exp, clip):
    if exp in BOX_ENS:                                # 두 벌 다 있어야 완성
        parts = [box_dump_read(m, clip) for m in BOX_ENS[exp]]
        return None if any(p is None for p in parts) else _merge_rows(parts)
    f = box_dump_path(exp, clip)
    return _read_jsonl(f) if f.is_file() else None


def box_dump_partial(exp, clip):
    """아직 도는 중인 덤프의 '지금까지' 와 진행률. 다 되기를 기다리지 않고 보여 주려는 것이다.
    exp_boxdump.py 가 사건 구간부터 훑으므로 초반 결과만으로도 검수가 된다."""
    if exp in BOX_ENS:                                # 끝난 벌은 완성본, 도는 벌은 중간본을 합친다. 진행률은 느린 쪽
        parts, pcts = [], []
        for m in BOX_ENS[exp]:
            full = box_dump_read(m, clip)
            if full is not None:
                parts.append(full); pcts.append(100)
            else:
                r_, p_ = box_dump_partial(m, clip)
                parts.append(r_ or []); pcts.append(p_ or 0)
        return (_merge_rows(parts) or None), min(pcts)
    d = box_dump_path(exp, clip).parent
    part = d / (clip + ".jsonl.part")
    prog = d / (clip + ".progress")
    rows = _read_jsonl(part) if part.is_file() else None
    pct = None
    if prog.is_file():
        try:
            p = json.loads(prog.read_text(encoding="utf-8"))
            if p.get("total"):
                pct = round(100.0 * p.get("done", 0) / p["total"])
        except Exception:
            pass
    return rows, pct


def box_dump_start(exp, clip):
    """덤프를 백그라운드로 만든다. 학습이 도는 중에도 추론 몇 GB 라 큐를 막지 않는다."""
    if exp in BOX_ENS:                                # 두 벌을 각각 만든다
        for m in BOX_ENS[exp]:
            box_dump_start(m, clip)
        return box_state(exp, clip)
    key = (exp, clip)
    if box_dump_path(exp, clip).is_file():
        return "done"
    if _BOXJOBS.get(key) == "run":
        return "run"
    _BOXJOBS[key] = "run"

    def work():
        import subprocess as _sp
        try:
            r = _sp.run([str(G / ".venv/bin/python"), str(G / "scripts/exp_boxdump.py"), exp, clip],
                        capture_output=True, text=True, cwd=str(G), timeout=3600)
            if box_dump_path(exp, clip).is_file():
                _BOXJOBS[key] = "done"
            else:
                _BOXJOBS[key] = "err:" + ((r.stdout or "") + (r.stderr or ""))[-200:]
        except Exception as e:
            _BOXJOBS[key] = "err:" + str(e)[:200]

    threading.Thread(target=work, daemon=True).start()
    return "run"


# ---------- 영상 검수: 미리 계산한 결과만 읽는다(2026-09-28) ----------
# 검수 탭은 모델을 눌러도 추론하지 않는다. scripts/review_cache.py 가 '지금 데이터' 로 끝난 판을 채점과 같은 판정 모듈로
# 영상 끝까지 돌려 dumps/review/<실험>/<best|last>/<항목>/ 에 둔 것을 그대로 내준다. 대상 판 고르기 · 작업 PC 채점 읽기도 그 파일 한 곳에 있다.
RV_ITEM = {"fire": "fire", "intrusion": "intrusion", "loiter": "loitering", "fall": "falldown"}   # 검수 탭 항목 → 저장 폴더(쓰러짐은 사람 검출 모델과 무관)
_RV_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


# ---------------------------------------------------------------- 히스토리 탭(2026-09-30): 모델 개선 기록, 사용자가 고친다
HISTORY = G / "configs/history.yaml"
CONTRACT_VER = 5                                       # ml_changelog.md 맨 위 vN 과 같아야 한다(scripts/check_contract.py 가 대조)
HS_ST, HS_DEC = ("할 일", "진행", "완료"), ("채택", "기각", "보류")   # 계약 v3(2026-10-01): 아이디어 삭제. 할지 덜 정한 것도 할 일 + cond, 판정으로 가른다
HS_ITEM = ("방화", "사람", "쓰러짐", "공통")
HS_KEYS = ("id", "s", "dec", "t", "why", "sub", "ref", "cond", "carry", "item", "phase")


def _phases():
    """단계 코드 → 화면 이름표(configs/result_blocks.yaml phases). 못 읽으면 빈 사전"""
    try:
        import yaml
        return (yaml.safe_load((G / "configs/result_blocks.yaml").read_text(encoding="utf-8")) or {}).get("phases") or {}
    except Exception:
        return {}
HS_EDIT = os.environ.get("VMS_HISTORY_EDIT") == "1"   # 고칠 수 있는 원본은 한 서버만(서버 B, dash.sh 가 켬). 다른 서버는 보기만 → 두 곳이 갈라지지 않게


def history_read():
    import yaml
    if not HISTORY.is_file():
        return {"error": "configs/history.yaml 이 없습니다"}
    d = yaml.safe_load(HISTORY.read_text(encoding="utf-8")) or {}
    d["updated_at"] = str(d.get("updated_at") or "")
    days = []
    for day in d.get("days") or []:
        day["date"] = str(day.get("date"))
        day["items"] = day.get("items") or []
        days.append(day)
    d["days"] = sorted(days, key=lambda x: x["date"], reverse=True)
    d["readonly"] = not HS_EDIT
    d["phases"] = _phases()                              # 화면 배지 · 고르기 칸용(파일에는 안 들어간다)
    return d


def _hs_clean(doc):
    """저장 전 모양 검사. 모르는 칸은 버리고, 값이 틀리면 ValueError"""
    days, phases = [], _phases()
    for day in doc.get("days") or []:
        date = str(day.get("date") or "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise ValueError(f"날짜 모양: {date}")
        items = []
        for it in day.get("items") or []:
            it = {k: str(it[k]).strip() for k in HS_KEYS if it.get(k) not in (None, "")}
            if not it.get("t") or not it.get("id"):
                raise ValueError("항목 이름 · id 가 비었다")
            if it.get("s") not in HS_ST:
                raise ValueError(f"상태: {it.get('s')}")
            if it.get("dec") and (it["dec"] not in HS_DEC or it["s"] != "완료"):
                raise ValueError(f"판정은 완료 항목에만(채택 · 기각 · 보류): {it['t'][:30]}")
            if it.get("item") and it["item"] not in HS_ITEM:
                raise ValueError(f"item 은 방화 · 사람 · 쓰러짐 · 공통: {it['item']}")
            if it.get("phase") and it["phase"] not in phases:
                raise ValueError(f"phase 는 result_blocks.yaml phases 코드: {it['phase']}")
            items.append(it)
        ms = [{"at": str(m.get("at", "")).strip(), "text": str(m.get("text", "")).strip()} for m in day.get("milestones") or [] if m.get("text")]
        out = {"date": date}
        if day.get("note"):
            out["note"] = str(day["note"]).strip()
        if ms:
            out["milestones"] = ms
        out["items"] = items
        days.append(out)
    if len({d["date"] for d in days}) != len(days):
        raise ValueError("같은 날짜가 둘")
    ids = [it["id"] for d in days for it in d["items"]]
    if len(set(ids)) != len(ids):
        raise ValueError("같은 id 가 둘")
    return sorted(days, key=lambda x: x["date"], reverse=True)


def history_write(body):
    """문서 통째로 저장. body = {base: 읽었을 때의 updated_at, by, doc}. 그 사이 다른 곳에서 고쳤으면 저장하지 않는다(conflict)"""
    import yaml
    from datetime import datetime, timedelta, timezone
    if not HS_EDIT:
        return {"ok": False, "err": "이 서버는 히스토리를 보기만 합니다. 고치기는 서버 B 대시보드에서"}
    with _SAVE_LOCK:
        cur = history_read()
        if cur.get("error"):
            return {"ok": False, "err": cur["error"]}
        if str(body.get("base") or "") != cur["updated_at"]:
            return {"ok": False, "conflict": True}
        days = _hs_clean(body.get("doc") or {})
        doc = {"updated_at": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S"),
               "updated_by": str(body.get("by") or "사용자"), "days": days}
        head = "".join(ln for ln in HISTORY.read_text(encoding="utf-8").splitlines(True) if ln.startswith("#"))   # 칸 설명 주석은 남긴다
        tmp = HISTORY.with_suffix(".yaml.tmp")
        tmp.write_text(head + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100000), encoding="utf-8")
        tmp.replace(HISTORY)
    return {"ok": True, "doc": history_read()}


def _rc():
    import sys as _s
    if str(G / "scripts") not in _s.path:
        _s.path.insert(0, str(G / "scripts"))
    import review_cache as RC
    return RC


def _rv_json(f):
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except Exception:
        return None


def _rv_key(key):
    """'실험|best' → (실험, best). 경로에 쓰므로 모양을 먼저 본다."""
    exp, _, ck = (key or "").partition("|")
    base, _, v = ck.partition("+")                           # best+seam = best 에 판정기 기술을 붙인 결과(scripts/review_post.py)
    if not _RV_NAME.match(exp) or base not in ("best", "last", "배포") or (v and not re.match(r"^[A-Za-z]+$", v)):
        return None, None
    return exp, ck


def _fall_official():
    """쓰러짐 공식 채점 = 결과 탭 점수 카드와 같은 기준값(configs/result_blocks.yaml fall_ref)."""
    try:
        import yaml
        r = (yaml.safe_load((G / "configs/result_blocks.yaml").read_text(encoding="utf-8")) or {}).get("fall_ref") or {}
        return {"점수": r["f1"], "정검": r["tp"], "미검": r["fn"], "오검": r["fp"]}
    except Exception:
        return None


def review_models(tab_item):
    RC = _rc()
    item = RV_ITEM.get(tab_item)
    if not item:
        return {"models": []}
    if item == "falldown":                                   # 쓰러짐 = 배포 모델 하나(새로 학습하지 않는다, 09-29 사용자)
        d = RC.cache_dir(RC.FALL_EXP, RC.FALL_CK, item)
        s, pg = _rv_json(d / "summary.json"), _rv_json(d / "_progress.json")
        if not (s or pg):
            return {"models": []}
        key = RC.FALL_EXP + "|" + RC.FALL_CK
        return {"models": [{"key": key, "exp": RC.FALL_EXP, "ckpt": RC.FALL_CK, "res": 1280,
                            "data": ["yolo11x-pose(사전학습) + 판정망 3벌"], "ended": s and s.get("made"), "done": bool(s),
                            "progress": pg, "score": s and s.get("score"), "official": _fall_official()}],
                "groups": [{"id": "_top", "label": "상위권 (배포 모델)", "keys": [key]}]}
    ko = {v: k for k, v in RC.ITEM_OF.items()}[item]
    out = []
    for exp, m in RC.eligible():
        if ko not in RC.items_of(m):
            continue
        off = RC.official(exp)
        for ck in RC.CKPTS:
            d = RC.cache_dir(exp, ck, item)
            s = _rv_json(d / "summary.json")
            o = (off.get(ck) or {}).get(item)
            out.append({"key": exp + "|" + ck, "exp": exp, "ckpt": ck, "res": RC.res_of(m), "data": RC._datasets(m),
                        "ended": m.get("ended"), "done": RC.is_done(exp, m, ck, ko),
                        "progress": _rv_json(d / "_progress.json"), "score": s and s.get("score"),
                        "official": o and {k: o[k] for k in ("점수", "정검", "미검", "오검")}})
    groups = [_rv_top(item, out)]                            # 맨 앞 = 상위권(점수 상위 3 + 판정기 기술), 뒤 = 결과 탭 블록
    try:
        import yaml
        have = {m["exp"] for m in out}
        cfg = yaml.safe_load((G / "configs/result_blocks.yaml").read_text(encoding="utf-8")) or {}
        import results_newdata as _RN
        _E = _RN._entries()
        for b in cfg.get("blocks") or []:
            runs = [b["control"], *b["runs"]]
            if have & set(runs):
                ph = (cfg.get("phases") or {}).get(_RN.block_phase(b, _E))   # 묶음 단계 = 견주는 실험들의 공통 단계(결과 탭과 같은 규칙)
                groups.append({"id": b["id"], "label": f"[{b.get('date', '')}] {b.get('title', '')}" + (f" · {ph}" if ph else ""), "runs": runs})
    except Exception:
        groups = []
    return {"models": out, "groups": groups}


def _rv_top(item, out):
    """상위 3개 판(작업 PC 공식 점수 순)과, 그 판에 판정기 쪽 기술(조각 정리 · 겹침 제거 · 규칙 B …)을 붙인 결과.
    기술 결과는 검수 캐시 위에서 판정만 다시 돈 것(scripts/review_post.py). 없거나 낡았으면 뒤에서 계산한다"""
    RC = _rc()                                               # scripts 를 경로에 넣는다
    import review_post as RP
    tops = RP.top(item, out)
    keys = []
    for m in tops:
        keys.append(m["key"])
        for vid, v in RP.VARIANTS.get(item, {}).items():
            ck = m["ckpt"] + "+" + vid
            s = _rv_json(RC.cache_dir(m["exp"], ck, item) / "summary.json")
            out.append(dict(m, key=m["exp"] + "|" + ck, ckpt=ck, ckLabel=f"{m['ckpt']} + {v['label']}", variant=v["label"],
                            base=m["key"], done=RP.is_fresh(m["exp"], m["ckpt"], item, vid), progress=None,
                            score=s and s.get("score"), official=None))
            keys.append(m["exp"] + "|" + ck)
    RP.compute_missing(item, tops)
    return {"id": "_top", "label": f"상위권 (점수 상위 {len(tops)}개 + 판정기 기술)", "keys": keys}


def review_summary(key, tab_item):
    """편별 경보 · 판정 + 작업 PC 채점의 편별 판정(있으면)."""
    exp, ck = _rv_key(key)
    item = RV_ITEM.get(tab_item)
    if not exp or not item:
        return None
    RC = _rc()
    s = _rv_json(RC.cache_dir(exp, ck, item) / "summary.json")
    if not s:
        return None
    if item == "falldown":
        s["official"] = _fall_official()
    o = (RC.official(exp).get(ck) or {}).get(item)          # 기술을 붙인 결과(best+seam)는 공식 채점이 없다
    if o:
        s["official"] = {k: o[k] for k in ("점수", "정검", "미검", "오검")}
        for c, r in (s.get("clips") or {}).items():
            r["official"] = o["bad"].get(c, "정검")       # 작업 PC 가 틀린 편만 적어 두므로 나머지는 정검
    return s


def review_clip_path(key, tab_item, clip):
    exp, ck = _rv_key(key)
    item = RV_ITEM.get(tab_item)
    if not exp or not item or not _RV_NAME.match(clip or ""):
        return None
    f = _rc().cache_dir(exp, ck, item) / (clip + ".json")
    return f if f.is_file() else None


def clip_info(clip):
    """클립 mp4 의 fps·총프레임·해상도 + XML 의 화재 발생 구간. 없으면 None."""
    if clip in _CI:
        return _CI[clip]
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return None
    import cv2
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    cap.release()
    _CI[clip] = {"clip": clip, "fps": round(fps, 4), "frames": n,
                 "dur": round(n / fps, 2) if fps else 0, "W": w, "H": h,
                 "fire": fire_spans(clip, fps)}
    return _CI[clip]


def read_frame(clip, sec, w=0):
    """그 시각(초)의 프레임 한 장을 JPEG 바이트로. 없으면 None. w 를 주면 그 가로 픽셀로 줄인다(썸네일). 디스크 캐시 우선."""
    _c = frame_cache_path(clip, sec, w)
    try:
        if _c.exists():
            return _c.read_bytes()
    except Exception:
        pass
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return None
    import cv2
    # ponytail: 요청마다 열고 seek 한다(초당 몇 장이면 충분). 느려지면 최근 캡처 하나만 재사용하도록 고친다.
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(float(sec) * fps)), 0))
    ok, fr = cap.read()
    cap.release()
    if not ok:
        return None
    data = _encode(fr, w)
    if data is None:
        return None
    try:                                                   # 다음 요청은 디코딩 없이
        _c.parent.mkdir(parents=True, exist_ok=True)
        _t = _c.with_suffix(f".tmp{os.getpid()}")
        _t.write_bytes(data); _t.replace(_c)
    except Exception:
        pass
    return data


def torch_device():
    """쓸 수 있는 가장 빠른 장치. cuda > mps(애플 실리콘) > cpu.

    맥북에서 라벨하며 전파까지 돌리려는 경우가 있다(2026-09-22). 예전에는 cuda 가 없으면
    무조건 cpu 라 전파 한 번에 몇 분이 걸렸다. MPS 는 지원 안 되는 연산이 남아 있어
    PYTORCH_ENABLE_MPS_FALLBACK 으로 그것만 cpu 로 흘린다.
    """
    import os
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        return "mps"
    return "cpu"


def torch_free(dev):
    """장치 캐시 비우기. cuda 가 아니면 할 일이 없거나 방법이 다르다."""
    import torch
    if dev == "cuda":
        torch.cuda.empty_cache()
    elif dev == "mps" and hasattr(torch, "mps"):
        try:
            torch.mps.empty_cache()
        except Exception:
            pass


_SAM2 = None
SAM2_ID = "facebook/sam2.1-hiera-small"


_CONDS = {}      # 카테고리별 조건(clip_conds) 캐시


def clip_conds(cat):
    """카테고리 안 클립들의 촬영 조건. {stem: {"tod","snow","rain","fog","loc","gt"}}
    같은 이름 XML 에서 읽는다(KISA 배포·연구개발 영상 공통 형식). 없으면 빈 dict."""
    if cat in _CONDS:
        return _CONDS[cat]
    import xml.etree.ElementTree as ET
    base = under_raw(cat)
    out = {}
    if base is not None and base.is_dir():
        for x in base.rglob("*.xml"):
            try:
                r = ET.parse(x).getroot()
            except Exception:
                continue
            tod = (r.findtext(".//TimeOfDay") or "").strip()
            if not tod and r.find(".//Alarm") is None:
                continue
            gt = None
            al = r.find(".//Alarm")
            if al is not None and al.findtext("StartTime"):
                try:
                    h, m, sec = al.findtext("StartTime").split(":")
                    gt = int(h) * 3600 + int(m) * 60 + int(sec)
                except Exception:
                    gt = None
            out[x.stem] = {"tod": tod, "gt": gt,
                           "snow": (r.findtext(".//Snow") or "").strip(),
                           "rain": (r.findtext(".//Rain") or "").strip(),
                           "fog": (r.findtext(".//Fog") or "").strip(),
                           "loc": (r.findtext(".//Location") or "").strip()}
    _CONDS[cat] = out
    return out


FRAME_CACHE = CACHE_DIR / "frames"


def frame_cache_path(clip, sec, w):
    import hashlib
    key = f"{clip}|{float(sec):.2f}|{int(w or 0)}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return FRAME_CACHE / h[:2] / (h + ".jpg")


def _encode(fr, w):
    import cv2
    q = 92
    if w and 0 < int(w) < fr.shape[1]:
        wh = int(round(fr.shape[0] * int(w) / fr.shape[1]))
        fr = cv2.resize(fr, (int(w), wh), interpolation=cv2.INTER_AREA)
        q = 78
    ok, buf = cv2.imencode(".jpg", fr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
    return buf.tobytes() if ok else None


def warm_frames(clip, ts, w=0):
    """영상을 한 번만 순차로 훑으며 ts(초 목록) 프레임을 전부 캐시에 채운다.
    프레임마다 seek 하는 것보다 훨씬 빠르다(격자 81장 기준)."""
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return 0
    want = {}
    for t in ts:
        pth = frame_cache_path(clip, t, w)
        if not pth.exists():
            want[round(float(t), 2)] = pth
    if not want:
        return 0
    import cv2
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    idx_of = {int(round(t * fps)): pth for t, pth in want.items()}
    if not idx_of:
        cap.release(); return 0
    start = min(idx_of); end = max(idx_of)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(start, 0))       # 시작 지점으로 한 번만 탐색
    i = start; n = 0
    while i <= end:
        ok = cap.grab()                                    # 필요 없는 프레임은 디코딩하지 않는다
        if not ok:
            break
        if i in idx_of:
            ok2, fr = cap.retrieve()
            if ok2:
                data = _encode(fr, w)
                if data:
                    pth = idx_of[i]
                    pth.parent.mkdir(parents=True, exist_ok=True)
                    tmp = pth.with_suffix(f".tmp{os.getpid()}")
                    tmp.write_bytes(data); tmp.replace(pth); n += 1
        i += 1
    cap.release()
    return n


_SAM2V = None
SAM2V_ID = "facebook/sam2.1-hiera-small"


def _read_frames(clip, t0, t1, step):
    """[t0, t1] 구간을 step 간격으로 읽어 RGB 목록과 시각 목록을 낸다. 순차 훑기라 탐색이 한 번뿐이다."""
    import cv2
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return [], [], 0, 0
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    want = {}
    t = t0
    while t <= t1 + 1e-6:
        want[int(round(t * fps))] = round(t, 2)
        t = round(t + step, 3)
    if not want:
        cap.release(); return [], [], 0, 0
    lo, hi = min(want), max(want)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(lo, 0))
    frames, times = [], []
    i = lo
    while i <= hi:
        if not cap.grab():
            break
        if i in want:
            ok, fr = cap.retrieve()
            if ok:
                frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)); times.append(want[i])
        i += 1
    H, W = (frames[0].shape[0], frames[0].shape[1]) if frames else (0, 0)
    cap.release()
    return frames, times, W, H


_FRAME_PREP = {}                # (clip, 초) → dict(w0, h0, rgb, orig, resh). 프레임 디코딩·전처리 결과


def _prep_frame(clip, sec):
    """프레임을 한 번만 읽고 전처리해 둔다. 같은 프레임에서 여러 번 클릭할 때 1.4초+0.9초를 아낀다."""
    import cv2, numpy as np
    key = (clip, round(float(sec), 2))
    hit = _FRAME_PREP.get(key)
    if hit is not None:
        return hit
    fr = None
    if str(clip).startswith("img:"):                       # 정지 이미지: 'img:data/원본데이터/.../x.jpg' (vms 기준 상대경로)
        ip = G / str(clip)[4:]
        try:
            ok = ip.is_file() and WS in ip.resolve().parents
        except Exception:
            ok = False
        if not ok:
            return None
        fr = cv2.imdecode(np.frombuffer(ip.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        if fr is None:
            return None
    _c = frame_cache_path(clip, sec, 0)
    if fr is None and _c.exists():
        fr = cv2.imdecode(np.frombuffer(_c.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if fr is None:
        mp4 = under_raw(clip, ".mp4")
        if mp4 is None or not mp4.exists():
            return None
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(float(sec) * fps)), 0))
        ok, fr = cap.read(); cap.release()
        if not ok:
            return None
    h0, w0 = fr.shape[:2]
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    proc, model, dev = _SAM2
    import torch
    with torch.no_grad():
        inp = proc(images=rgb, return_tensors="pt").to(dev)
        emb = model.get_image_embeddings(inp["pixel_values"])
    resh = inp["reshaped_input_sizes"][0].tolist() if "reshaped_input_sizes" in inp else [1024, 1024]
    out = dict(w0=w0, h0=h0, orig=inp["original_sizes"], resh=resh, emb=emb)
    if len(_FRAME_PREP) >= 24:
        _FRAME_PREP.pop(next(iter(_FRAME_PREP)))
    _FRAME_PREP[key] = out
    return out


def _mask_bbox(m, min_frac=0.05, min_px=20):
    """이진 마스크의 박스. 잡티 제외: 연결 성분 중 가장 큰 성분 넓이의 min_frac 이상인 것만 모아 박스를 잡는다.
    반환 (x1, y1, x2, y2) 픽셀, 없으면 None."""
    import cv2, numpy as np
    m8 = (m > 0).astype("uint8")
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
    if n <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = int(areas.max())
    if big < min_px:
        return None
    keep = [i + 1 for i, a in enumerate(areas) if a >= max(min_px, big * min_frac)]
    sel = np.isin(lab, keep)
    ys, xs = np.nonzero(sel)
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def sam2_mask_pts(clip, sec, pts, box=None):
    """포함/제외 점 여러 개(또는 박스 하나)로 마스크.
    pts = [[x, y, label], ...] (정규화, label 1=포함 0=제외) · box = [x, y, w, h] 정규화
    반환 (박스[정규화 x,y,w,h], 외곽선, 점수)"""
    global _SAM2
    import cv2, numpy as np, torch
    if not pts and not box:
        return None, None, 0.0
    if _SAM2 is None:
        from transformers.models.sam2.processing_sam2 import Sam2Processor
        from transformers.models.sam2.modeling_sam2 import Sam2Model
        dev = torch_device()
        _SAM2 = (Sam2Processor.from_pretrained(SAM2_ID),
                 Sam2Model.from_pretrained(SAM2_ID).to(dev).eval(), dev)
    proc, model, dev = _SAM2
    P = _prep_frame(clip, sec)
    if P is None:
        return None, None, 0.0
    w0, h0 = P["w0"], P["h0"]
    sx, sy = P["resh"][1] / w0, P["resh"][0] / h0        # 전처리가 하는 좌표 스케일(리사이즈 입력 기준)
    kw = {}
    if pts:
        kw["input_points"] = torch.tensor([[[[float(q[0]) * w0 * sx, float(q[1]) * h0 * sy] for q in pts]]], device=dev)
        kw["input_labels"] = torch.tensor([[[int(q[2]) for q in pts]]], device=dev)
    if box:
        kw["input_boxes"] = torch.tensor([[[float(box[0]) * w0 * sx, float(box[1]) * h0 * sy,
                                           (float(box[0]) + float(box[2])) * w0 * sx,
                                           (float(box[1]) + float(box[3])) * h0 * sy]]], device=dev)
    with torch.no_grad():
        out = model(image_embeddings=P["emb"], multimask_output=True, **kw)
        scores = out.iou_scores[0][0].float().cpu().numpy()
        best = int(np.argmax(scores)); score = float(scores[best])
        one = out.pred_masks[:, :, best:best + 1]              # 최고 마스크 1장만 업샘플(3장 → 1장)
        masks = proc.post_process_masks(one.cpu(), P["orig"])[0][0]
    m = masks[0].numpy().astype("uint8")
    bb = _mask_bbox(m)                                    # 잡티를 뺀 박스(윤곽선과 맞게)
    if bb is None:
        return None, None, score
    x1, y1, x2, y2 = bb
    bx = [round(x1 / w0, 5), round(y1 / h0, 5), round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)]
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    poly = []
    if cs:
        c = max(cs, key=cv2.contourArea)
        c = cv2.approxPolyDP(c, 0.003 * cv2.arcLength(c, True), True)
        poly = [[round(float(q[0][0]) / w0, 4), round(float(q[0][1]) / h0, 4)] for q in c]
    return bx, poly, score


PROP_DEFAULT_MODE = "separate"   # 전파 방식 기본값: separate(객체별 독립 세션) · joint(한 세션). eval_prop_modes.py 결과로 정한다
PROP_THR = {1: 0.0, 2: 0.0}      # 객체별 마스크 로짓 임계(독립 적용). 연기(2)를 낮추면 흐린 연기를 더 담는다


def _poly_of(arr, W, H, eps=0.004):
    """이진 마스크 → 가장 큰 윤곽선(정규화 좌표, 단순화). 화면에 객체별 층으로 그린다."""
    import cv2
    cs, _ = cv2.findContours((arr > 0).astype("uint8"), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return []
    c = max(cs, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, eps * cv2.arcLength(c, True), True)
    return [[round(float(q[0][0]) / W, 4), round(float(q[0][1]) / H, 4)] for q in c]


def _seed_inputs(sd, W, H):
    """참조샷 하나 → SAM2 비디오 세션 입력(픽셀 박스 + 있으면 포함/제외 점). 점만 있고 박스가 없는 참조도 된다."""
    kw = {}
    b = sd.get("box")
    if b:
        kw["input_boxes"] = [[[float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]]]
    pts = [q for q in (sd.get("pts") or []) if len(q) >= 3]
    if pts:
        kw["input_points"] = [[[[float(q[0]) * W, float(q[1]) * H] for q in pts]]]
        kw["input_labels"] = [[[int(q[2]) for q in pts]]]
    return kw


def sam2_propagate_objs(clip, seeds, back=5.0, fwd=10.0, step=0.5, progress=None, a=None, b=None, mode=None, thr=None):
    """여러 객체 전파. seeds = [{"t": 초, "box": [x,y,w,h], "obj": 번호, "pts": [[x,y,label],...]}]
    구간: a·b(초)를 주면 그 구간만(교정 전파), 없으면 참조샷 앞뒤 back·fwd 초.
    mode: separate(객체마다 독립 세션·독립 임계 → 서로 뭉개지지 않는다) · joint(한 세션에 전 객체)
    반환 ({시각: {obj: [x,y,w,h]}}, {시각: {obj: 윤곽선}}, 걸린초, 오류)"""
    global _SAM2V
    import numpy as np, torch, time
    mode = mode or PROP_DEFAULT_MODE
    thr = {int(k): float(v) for k, v in (thr or PROP_THR).items()}
    if not seeds:
        return {}, {}, 0, "참조샷 없음"
    ts = [float(x["t"]) for x in seeds]
    t0 = max(0.0, min(ts) - float(back)) if a is None else max(0.0, float(a))
    t1 = (max(ts) + float(fwd)) if b is None else float(b)
    seeds = [sd for sd in seeds if t0 - 1e-6 <= float(sd["t"]) <= t1 + 1e-6]   # 구간 밖 참조는 이번 전파에 안 쓴다
    if not seeds:
        return {}, {}, 0, "구간 안 참조샷 없음"
    frames, times, W, H = _read_frames(clip, t0, t1, float(step))
    if not frames:
        return {}, {}, 0, "프레임 없음"
    if _SAM2V is None:
        from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
        from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
        dev = torch_device()
        _SAM2V = (Sam2VideoProcessor.from_pretrained(SAM2V_ID),
                  Sam2VideoModel.from_pretrained(SAM2V_ID).to(dev).eval(), dev)
    proc, model, dev = _SAM2V
    tic = time.time()
    # 참조샷 사이 구간 단위 전파: 각 구간은 그 구간 시작 참조 박스 하나만 조건으로 두고 새 세션에서 돈다.
    # (transformers SAM2 비디오는 시작 프레임 이후에 넣어 둔 참조 박스를 실제로 쓰지 않아, 참조샷이 여러 장이어도 첫 장만 효과가 있었다)
    def fidx(t):
        return min(range(len(times)), key=lambda k: abs(times[k] - float(t)))
    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    out, polys = {}, {}
    if progress is not None:
        progress["total"] = len(frames) * (1 if mode == "joint" else len(by_obj)); progress["done"] = 0

    def area_at(prof, tsec):
        """참조샷 (시각, 넓이) 목록에서 tsec 의 기준 넓이(선형 보간, 밖은 가장 가까운 값)."""
        if not prof:
            return None
        if tsec <= prof[0][0]:
            return prof[0][1]
        if tsec >= prof[-1][0]:
            return prof[-1][1]
        for (t0, a0), (t1, a1) in zip(prof, prof[1:]):
            if t0 <= tsec <= t1:
                w = (tsec - t0) / (t1 - t0) if t1 > t0 else 0.0
                return a0 + (a1 - a0) * w
        return prof[-1][1]

    drops = {"lost": 0, "empty": 0, "size": 0}          # 건너뛴 사유별 수. 작업 상태(progress)에 실어 편집기가 보인다
    if progress is not None:
        progress["drops"] = drops

    def take(gi, oid, arr, prof):
        """한 프레임·한 객체의 이진 마스크 → 박스·윤곽선 기록. 참조 박스 넓이 대비 3배/1/3 밖이면 흘러간 것으로 버린다."""
        bb = _mask_bbox(arr)
        if bb is None:
            drops["empty"] += 1; return
        x1, y1, x2, y2 = bb
        area = (x2 - x1) * (y2 - y1)
        sa = area_at(prof, times[gi]) or area
        if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 3.0:
            drops["size"] += 1; return
        k = f"{times[gi]:.1f}"
        out.setdefault(k, {})[str(oid)] = [round(x1 / W, 5), round(y1 / H, 5), round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]
        polys.setdefault(k, {})[str(oid)] = _poly_of(arr, W, H)

    def tick():
        if progress is not None:
            if progress.get("cancel"):
                raise RuntimeError("cancelled")
            progress["done"] = min(progress.get("done", 0) + 1, progress["total"])

    def masks_of(r, oids):
        """전파 결과 한 프레임 → {obj: 이진 마스크}. 객체마다 자기 임계로 독립 이진화(argmax 없음 → 불·연기가 서로를 지우지 않는다)."""
        pm = r.pred_masks.cpu().float()                 # (객체수, 1, 256, 256)
        if pm.ndim == 4:
            pm = pm.unsqueeze(0)                        # 프로세서는 (영상 1, 객체수, 1, h, w) 를 받아 [0] → (객체수, 1, H, W) 를 준다
        sc = r.object_score_logits
        res = {}
        for j, oid in enumerate(oids):
            if sc is not None and sc.numel() > j and float(sc.detach().flatten()[j]) <= 0:   # 대상 없음(가림·이탈)
                drops["lost"] += 1; continue
            one = pm[:, j:j + 1] if pm.shape[1] > j else pm
            m = proc.post_process_masks(one, [(H, W)], binarize=True, mask_threshold=thr.get(oid, 0.0))[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while arr.ndim > 2:
                arr = arr[0]
            res[oid] = arr
        return res

    def run_segment(inputs, i0, i1, seed_i, profs, rev):
        """frames[i0..i1] 구간. inputs = {obj: 참조샷} 를 seed_i 프레임에 조건으로 넣고 rev 방향으로 전파."""
        if i1 < i0 or not inputs:
            return
        sess = proc.init_video_session(video=frames[i0:i1 + 1], inference_device=dev, dtype=torch.float32)
        oids = sorted(inputs)
        if len(oids) == 1:                              # obj_ids 는 복사해서 넘긴다(프로세서가 넘긴 리스트를 비운다)
            proc.add_inputs_to_inference_session(sess, frame_idx=seed_i - i0, obj_ids=list(oids), original_size=(H, W), **_seed_inputs(inputs[oids[0]], W, H))
        else:                                           # 공동: 여러 객체를 한 번에(박스만). 객체마다 따로 넣으면 같은 프레임의 조건 기억이 비어 전파가 깨진다
            bxs = [_seed_inputs(inputs[o], W, H).get("input_boxes", [[[0, 0, 1, 1]]])[0][0] for o in oids]
            proc.add_inputs_to_inference_session(sess, frame_idx=seed_i - i0, obj_ids=list(oids), original_size=(H, W), input_boxes=[bxs])
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=seed_i - i0, reverse=rev):
            gi = i0 + int(r.frame_idx); tick()
            for oid, arr in masks_of(r, oids).items():
                take(gi, oid, arr, profs.get(oid) or [])
        del sess
        torch_free(dev)

    def prof_of(sds):
        return [(float(sd["t"]), float(sd["box"][2]) * W * float(sd["box"][3]) * H) for sd in sds if sd.get("box")]

    with torch.no_grad():
        if mode == "joint":
            # 공동: 참조 시각의 합집합으로 구간을 나누고, 각 구간 시작에 모든 객체를 한 세션에 넣는다(구간 시작에 참조가 없는 객체는 가장 가까운 참조 박스)
            profs = {oid: prof_of(sorted(sds, key=lambda sd: float(sd["t"]))) for oid, sds in by_obj.items()}
            tset = sorted({fidx(sd["t"]) for sd in seeds})
            def nearest(oid, i):
                return min(by_obj[oid], key=lambda sd: abs(fidx(sd["t"]) - i))
            run_segment({oid: nearest(oid, tset[0]) for oid in by_obj}, 0, tset[0], tset[0], profs, True)
            for k, i0 in enumerate(tset):
                i1 = (tset[k + 1] - 1) if k + 1 < len(tset) else (len(frames) - 1)
                run_segment({oid: nearest(oid, i0) for oid in by_obj}, i0, max(i0, i1), i0, profs, False)
        else:
            # 분리(기본): 객체마다 자기 세션. 구간 = [시작 → 첫 참조](역방향), [참조 k → 참조 k+1)(정방향), [마지막 참조 → 끝]
            for oid in sorted(by_obj):
                sds = sorted(by_obj[oid], key=lambda sd: float(sd["t"]))
                profs = {oid: prof_of(sds)}
                idxs = [fidx(sd["t"]) for sd in sds]
                run_segment({oid: sds[0]}, 0, idxs[0], idxs[0], profs, True)
                for k, sd in enumerate(sds):
                    i0 = idxs[k]
                    i1 = (idxs[k + 1] - 1) if k + 1 < len(sds) else (len(frames) - 1)
                    if k + 1 < len(sds) and idxs[k + 1] == i0:    # 같은 프레임에 참조가 둘이면 뒤 것만
                        continue
                    run_segment({oid: sd}, i0, max(i0, i1), i0, profs, False)
    # 모델이 한 번 어긋나면 이후 전파가 조용히 전부 "대상 없음"이 된다(2026-09-16 실측: 128프레임 중 126 lost).
    # 코드·입력이 같아도 같은 프로세스에서 계속 재현되고, 새로 올리면 정상으로 돌아온다 → 비워서 다음 작업이 다시 올리게 한다.
    #
    # 2026-09-23: 판정이 너무 넓었다. 원래 기준(놓침 >= 9 x 건진것)이 '사람이 화면 밖으로 나가서
    # 정상적으로 놓친 것' 까지 모델 고장으로 몰았다. 마케팅(PeopleCounting) 편 C00_283_0001 은
    # 2,653번 중 2,383 놓침(90%)이었지만 74프레임을 제대로 건졌고, C00_290_0001 은 74% 놓침에
    # 190프레임을 건졌다. 그런데 오류로 판정되는 바람에 그 결과가 통째로 버려졌다(_prop_worker
    # 가 err 이 있으면 저장을 안 한다). 사용자가 네 번 다시 돌려 9분씩 날렸다.
    #
    # 진짜 고장은 '건진 것이 사실상 없는' 모습이다(126/128 일 때 건진 것 2개).
    # 사람이 드나들어 놓치는 것은 건진 것이 꾸준히 남는다. 그래서 절대 개수로 가른다.
    n_lost, n_keep = drops["lost"], len(out)
    if n_keep <= 3 and n_lost >= 20:
        _SAM2V = None
        return out, polys, round(time.time() - tic, 1), "전파가 전부 실패했습니다. 모델을 다시 올렸으니 한 번 더 눌러 주세요"
    if n_lost >= 3 * max(1, n_keep):
        # 오류가 아니라 알림이다. 결과는 저장된다.
        # 모델은 그래도 비운다. 어긋난 모델이 이 구간에 걸쳐 조용히 나빠진 것일 수 있고,
        # 다시 올리는 값이 2초라 의심스러울 때 그냥 올리는 편이 싸다. 안 올리면
        # 다음 전파까지 나쁜 상태가 이어진다("아까는 잘 됐는데" 의 정체).
        _SAM2V = None
        if isinstance(progress, dict):
            progress["warn"] = ("구간 대부분에서 대상을 놓쳤습니다(%d/%d). 대상이 화면 밖으로 나가거나 "
                                "가려지거나, 너무 작아지면 이렇게 됩니다. 건진 %d프레임은 저장했습니다. "
                                "모델을 다시 올렸으니 같은 구간을 한 번 더 돌려 보고, "
                                "그래도 같으면 구간을 참조샷 근처로 짧게 잘라 보세요."
                                % (n_lost, n_lost + n_keep, n_keep))
    return out, polys, round(time.time() - tic, 1), None


_PROP_JOBS = {}                  # id → {"done","total","running","result","err","sec"}
_PROP_SEQ = [0]
SAM2_DIR = G / "data/학습데이터/자동라벨/sam2"
GT_DIR = G / "data/학습데이터/정답라벨"       # 데이터셋이 제공한 정답의 '복사본'(박스·점·이벤트). 원본 XML/JSON 은 읽기만 한다. 사람이 고치면 손라벨로 간다


def _hms(s):
    h, m, sec = str(s).strip().split(":"); return int(h) * 3600 + int(m) * 60 + float(sec)


def derive_gt(clip):
    """원본 옆 정답 파일(XML/JSON)을 읽어 정답라벨 저장소 형식 {frames, points, events, actions, ...} 으로 바꾼다. 원본은 건드리지 않는다.
    - AI허브 171 XML: 객체별 키프레임 점(x,y) → points, 행동 구간 → actions, 이벤트 → events
    - KISA XML(Alarm): events 만
    - AI허브 JSON(침입·쓰러짐 event_frame): events 만
    - AI허브 71953 다각도 JSON(폴더 단위, videos[] + annotations.caption[view]): 그 영상(view)의 설명·이벤트 종류 → meta
    반환 dict 또는 None(원본 정답 없음)."""
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None:
        return None
    stem = Path(clip).stem
    src_rel = None
    d = {"clip": stem, "frames": {}, "points": {}, "actions": {}, "events": [], "derived": True}
    fmt = (DATASETS.get(cat_of(clip)) or {}).get("gt") or ""     # 규격에 적힌 형식. 아래 분기는 형식별이고 데이터셋별이 아니다
    xml = under_raw(clip, ".xml")
    if fmt == "none":
        return None
    if xml is not None and xml.exists() and fmt in ("", "kisa_xml", "aihub171_xml"):
        import xml.etree.ElementTree as ET
        try:
            r = ET.parse(xml).getroot()
        except Exception:
            r = None
        if r is not None and r.find("object") is not None and r.find("object/position/keypoint") is not None:   # AI허브 171 형식
            W = int(r.findtext("size/width") or 0); H = int(r.findtext("size/height") or 0); fps = float(r.findtext("header/fps") or 30)
            for ev in r.findall("event"):
                try:
                    d["events"].append({"name": ev.findtext("eventname"), "start": _hms(ev.findtext("starttime")), "dur": _hms(ev.findtext("duration"))})
                except Exception:
                    pass
            for oi, ob in enumerate(r.findall("object"), 1):
                name = ob.findtext("objectname") or f"person_{oi}"
                m = re.search(r"(\d+)$", name); oid = int(m.group(1)) if m else oi
                for pos in ob.findall("position"):
                    kf = pos.findtext("keyframe"); kx = pos.findtext("keypoint/x"); ky = pos.findtext("keypoint/y")
                    if kf and kx and ky and W and H:
                        d["points"].setdefault(tkey(int(kf) / fps), {})[str(oid)] = [round(float(kx) / W, 5), round(float(ky) / H, 5)]
                acts = []
                for a in ob.findall("action"):
                    for fr in a.findall("frame"):
                        try:
                            acts.append({"name": a.findtext("actionname"), "start": int(fr.findtext("start")) / fps, "end": int(fr.findtext("end")) / fps})
                        except Exception:
                            pass
                d["actions"][str(oid)] = acts
            d.update({"src": "aihub171", "W": W, "H": H, "fps": fps, "note": "AI허브 171: 박스 없음. 객체별 키프레임 점 → SAM 탭 자리"})
        else:                                                                       # KISA XML: 발생 시각·경보 구간
            d["events"] = [{"name": e.get("kind") or "alarm", "start": e["start"], "dur": e.get("dur", 0)} for e in fire_spans(clip)]
            d["src"] = "kisa_xml"
        src_rel = str(xml.relative_to(G))
    else:
        js = under_raw(clip, ".json")
        if js is not None and js.exists():                                          # 같은 이름 JSON(AI허브 침입·쓰러짐)
            d["events"] = [{"name": e.get("kind") or "event", "start": e["start"], "dur": e.get("dur", 0), "note": e.get("note", "")} for e in json_spans(clip)]
            d["src"] = "aihub_json"; src_rel = str(js.relative_to(G))
        else:                                                                       # 폴더 단위 JSON(AI허브 71953 다각도): videos[].filename 이 이 영상인 것
            for cand in sorted(mp4.parent.glob("*.json")):
                try:
                    j = json.loads(cand.read_text(encoding="utf-8"))
                except Exception:
                    continue
                vids = j.get("videos") if isinstance(j.get("videos"), list) else []
                hit = next((v for v in vids if Path(str(v.get("filename", ""))).stem == stem), None)
                if hit is None:
                    continue
                ann = j.get("annotations") or {}
                view = hit.get("view") or ""
                cap = (ann.get("caption") or {}).get(view, {}) if isinstance(ann.get("caption"), dict) else {}
                evd = (ann.get("evidence") or {}).get(view, {}) if isinstance(ann.get("evidence"), dict) else {}
                W = int(hit.get("width") or 0); H = int(hit.get("height") or 0)
                ci = clip_info(clip) or {}; fps = float(ci.get("fps") or 30.0)
                # 근거 박스: frame_id[k] 프레임의 obj_bbox[k] = [x1,y1,x2,y2] 픽셀 → 정답 박스(정규화). 키프레임 몇 장뿐이라 참조샷 재료로 쓴다
                for k, fid in enumerate(evd.get("frame_id") or []):
                    try:
                        x1, y1, x2, y2 = [float(v) for v in evd["obj_bbox"][k]]
                        oid = str(evd.get("obj_id", [])[k] if k < len(evd.get("obj_id", [])) else k + 1)
                        if W and H:
                            d["frames"].setdefault(tkey(int(fid) / fps), {})[oid] = [round(x1 / W, 5), round(y1 / H, 5), round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]
                    except Exception:
                        pass
                m = re.search(r"(\d+)\s*~\s*(\d+)", str(evd.get("evidence_text") or ""))          # "프레임 범위 221~602" → 이벤트 구간
                if m:
                    d["events"].append({"name": ann.get("event_class") or "event", "start": round(int(m.group(1)) / fps, 1), "dur": round((int(m.group(2)) - int(m.group(1))) / fps, 1)})
                d.update({"src": "aihub71953", "W": W, "H": H, "fps": fps,
                          "meta": {"event_class": ann.get("event_class"), "view": view, "time": hit.get("time"), "date": hit.get("date"),
                                   "cctv_angle": hit.get("cctv_angle"), "caption": cap.get("caption_text"), "cot": cap.get("cot")},
                          "note": "AI허브 71953 다각도: 근거 키프레임 박스 몇 장 + 설명문. 나머지 프레임은 SAM 으로 만든다"})
                src_rel = str(cand.relative_to(G)); break
    if src_rel is None:
        return None
    d["src_file"] = src_rel
    return d


def gt_of(clip):
    """정답라벨 저장소 읽기. 없으면 원본 정답에서 만들어(복사본) 저장소에 넣고 준다. 원본 파일은 읽기만."""
    f = GT_DIR / (Path(clip).stem + ".json")
    d = read_json(f, None)
    if d is not None:
        return d
    d = derive_gt(clip)
    if d is None:
        return {"frames": {}, "points": {}, "events": [], "actions": {}}
    try:
        write_json(f, d)
    except Exception:
        pass
    return d


_PROP_Q = []                     # 대기 중인 job id (순서대로)
_PROP_LOCK = threading.Lock()
_PROP_WORKER = [None]            # 워커 스레드 하나 (GPU 공유·메모리 때문에 전파는 한 번에 하나)


def _prop_worker():
    import time as _t
    while True:
        with _PROP_LOCK:
            if not _PROP_Q:
                _PROP_WORKER[0] = None
                return
            jid = _PROP_Q.pop(0)
        st = _PROP_JOBS[jid]
        if st.get("cancel"):
            st["state"] = "done"; st["running"] = False; st["err"] = "cancelled"; continue
        st["state"] = "running"; st["running"] = True; st["started"] = _t.time()
        try:
            frames, polys, sec, err = sam2_propagate_objs(st["clip_full"], st["seeds"], step=st["step"], progress=st,
                                                          a=st.get("a"), b=st.get("b"), mode=st.get("mode"))
            st["nframes"] = len(frames); st["err"] = err; st["sec"] = sec
            if frames and not err:                       # 서버가 바로 저장 → 브라우저가 떠나 있어도 결과가 남는다
                sam2_store_write(st["clip_full"], frames, [{"t": q["t"], "obj": q.get("obj", 1), "box": q.get("box")} for q in st["seeds"]], polys)
                st["saved"] = True
        except Exception as e:
            st["err"] = str(e)
        finally:
            st["running"] = False; st["state"] = "done"; st["ended"] = _t.time()
            with _PROP_LOCK:                             # 끝난 작업은 최근 50개만 남긴다
                done = [j for j, x in _PROP_JOBS.items() if x.get("state") == "done"]
                for j in done[:-50]:
                    _PROP_JOBS.pop(j, None)


def prop_job_start(clip, seeds, a, b, step, mode=None):
    """전파 작업을 큐에 넣고 id 를 준다. 같은 클립이 이미 대기·진행 중이면 None(새 참조샷을 조용히 버리지 않는다)."""
    with _PROP_LOCK:
        for st0 in _PROP_JOBS.values():
            if st0.get("clip") == Path(clip).stem and st0.get("state") in ("queued", "running"):
                return None
        _PROP_SEQ[0] += 1
        jid = str(_PROP_SEQ[0])
        st = _PROP_JOBS[jid] = {"id": jid, "clip": Path(clip).stem, "clip_full": clip, "seeds": seeds, "a": a, "b": b, "step": step, "mode": mode,
                                "done": 0, "total": 0, "running": True, "state": "queued", "nframes": 0, "err": None, "sec": 0, "saved": False}
        _PROP_Q.append(jid)
        print(f"[전파 시작] {Path(clip).stem} 구간 {a}~{b} step {step} 참조샷 {sorted({round(float(q.get('t',0)),1) for q in seeds})}", flush=True)   # dash.log 에 남긴다
        if _PROP_WORKER[0] is None or not _PROP_WORKER[0].is_alive():
            _PROP_WORKER[0] = threading.Thread(target=_prop_worker, daemon=True)
            _PROP_WORKER[0].start()
    return jid


def prop_jobs_view(stem=None):
    """클립(또는 전체) 전파 작업 목록: 대기 순번·진행률·오류. 결과 본문은 뺀다."""
    out = []
    with _PROP_LOCK:
        q = list(_PROP_Q); items = list(_PROP_JOBS.items())   # 스냅샷 뒤 순회(순회 중 삽입 방지)
    for jid, st in items:
        if stem and st.get("clip") != stem:
            continue
        out.append({"id": jid, "clip": st.get("clip"), "state": st.get("state", "done" if not st.get("running") else "running"),
                    "pos": (q.index(jid) + 1) if jid in q else 0, "done": st.get("done", 0), "total": st.get("total", 0),
                    "err": st.get("err"), "warn": st.get("warn"), "saved": st.get("saved", False), "sec": st.get("sec", 0), "nframes": st.get("nframes", 0), "mode": st.get("mode"),
                    "drops": st.get("drops") or {}, "a": st.get("a"), "b": st.get("b"), "step": st.get("step"),
                    "seed_ts": sorted({round(float(q.get("t", 0)), 1) for q in (st.get("seeds") or [])})})   # 어느 구간·어느 참조샷으로 돌았는지(사후 확인용)
    return out


def _sam2_file(clip):
    return SAM2_DIR / (Path(clip).stem + ".json")


def _sam2_load(clip):
    d = read_json(_sam2_file(clip), {"clip": Path(clip).stem})
    d.setdefault("frames", {}); d.setdefault("polys", {}); d.setdefault("seeds", [])
    return d


def sam2_store_clear(clip):
    f = _sam2_file(clip)
    if not f.exists():
        return 0
    d = _sam2_load(clip)
    n = len(d["frames"])
    d["frames"] = {}; d["polys"] = {}   # 결과만 비우고 참조샷(seeds)은 남긴다 → 지우고 다시 전파 가능. 완전 초기화는 clearlabels
    write_json(f, d)
    return n


def sam2_store_write(clip, frames, seeds, polys=None):
    """전파 결과(박스·윤곽선)를 자동라벨/sam2/<클립>.json 에 합친다(같은 시각·같은 객체는 덮어쓴다). 참조샷도 기록.
    손라벨 박스가 있는 프레임은 손라벨만 쓰므로 건너뛴다."""
    d = _sam2_load(clip)
    hand = _hand_box_frames(clip)
    for t, objs in (frames or {}).items():
        k = tkey(t)
        if k in hand or not isinstance(objs, dict):
            continue
        d["frames"][k] = {**(d["frames"].get(k) or {}), **objs}
        if polys and polys.get(t):
            d["polys"][k] = {**(d["polys"].get(k) or {}), **polys[t]}
    have = {(round(float(x.get("t", 0)), 2), int(x.get("obj", 1))) for x in d["seeds"]}
    for sd in seeds or []:
        k = (round(float(sd.get("t", 0)), 2), int(sd.get("obj", 1)))
        if k not in have:
            d["seeds"].append({"t": sd.get("t"), "obj": sd.get("obj", 1), "box": sd.get("box")}); have.add(k)
    d["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(_sam2_file(clip), d)
    return len(d["frames"])


def _hand_box_frames(clip):
    """그 클립에서 손라벨 박스(cls>=0)가 있는 프레임 키 집합. 사람·화재 손라벨 파일 둘 다 본다."""
    stem = Path(clip).stem; out = set()
    for kind in ("person", "fire"):
        for r in read_json(label_file(kind), []):
            if Path(str(r.get("clip", ""))).stem == stem and int(r.get("cls", -1)) >= 0:
                out.add(tkey(r.get("t", 0)))
    return out


def sam2_store_drop(clip, t):
    f = _sam2_file(clip)
    if not f.exists():
        return 0
    d = _sam2_load(clip)
    k = tkey(t)
    n = 1 if k in d["frames"] else 0
    d["frames"].pop(k, None); d["polys"].pop(k, None)
    write_json(f, d)
    return n


def sam2_store_drop_obj(clip, obj):
    """한 객체의 전파 결과·참조샷을 저장소 전 프레임에서 뺀다. 그 객체만 있던 프레임은 프레임째 사라진다."""
    f = _sam2_file(clip)
    if not f.exists():
        return 0
    d = _sam2_load(clip); o = str(obj); n = 0
    for key in ("frames", "polys"):
        m = d[key]
        for k in list(m):
            if o in (m[k] or {}):
                m[k].pop(o); n += (key == "frames")
            if not m[k]:
                m.pop(k)
    d["seeds"] = [q for q in d["seeds"] if str(q.get("obj")) != o]
    write_json(f, d)
    return n


def _locked_store(fn):
    """sam2 저장소는 read-modify-write. 전파 워커·검수 ×·일괄 삭제가 겹쳐도 한쪽이 사라지지 않게 savelabel 과 같은 락을 쓴다."""
    def w(*a, **k):
        with _SAVE_LOCK:
            return fn(*a, **k)
    w.__name__ = fn.__name__
    return w


sam2_store_write = _locked_store(sam2_store_write)
_sam2_store_drop_raw = sam2_store_drop            # savelabel 은 이미 _SAVE_LOCK 안 → 락 없는 원본으로
sam2_store_drop = _locked_store(sam2_store_drop)
sam2_store_drop_obj = _locked_store(sam2_store_drop_obj)
sam2_store_clear = _locked_store(sam2_store_clear)


def train_progress(name):
    """logs/queue/<실험>.log 끝에서 ultralytics 진행줄과 마지막 검증줄을 읽는다.
    진행줄: '  28/80  84.8G  1.132 0.926 1.191  325  640: 81% ━━ 1377/1681 1.9it/s 11:25<2:36'  (\r 로 갱신되는 한 줄)
    검증줄: '  all  601  798  0.827  0.731  0.83  0.578'  (이미지 수, 박스 수, P, R, mAP50, mAP50-95)"""
    f = G / "logs/queue" / f"{name}.log"
    if not f.is_file():
        return None
    try:
        with open(f, "rb") as fh:
            fh.seek(max(0, f.stat().st_size - 200_000)); tail = fh.read().decode("utf-8", "ignore")
    except Exception:
        return None
    tail = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", tail)                   # 색·커서 제어 제거
    lines = [l for l in re.split(r"[\r\n]+", tail) if l.strip()]
    prog = None
    for l in reversed(lines):
        m = re.search(r"^\s*(\d+)/(\d+)\s+([\d.]+G)\s+(?:[\d.]+\s+){3}\d+\s+\d+:\s*(\d+)%.*?(\d+)/(\d+)\s+([\d.]+)(it/s|s/it)\s+(\S+?)<(\S+)", l)
        if m:
            prog = m; break
    if not prog:
        return {"name": name, "state": "준비 중(라벨 스캔·캐시)"}
    ep, eps, mem, pct, it, its, sp, unit, used, eta = prog.groups()
    ep, eps, it, its, sp = int(ep), int(eps), int(it), int(its), float(sp)
    it_s = sp if unit == "it/s" else (1.0 / sp if sp else 0)
    val = None
    for l in reversed(lines):
        m = re.search(r"^\s*all\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", l)
        if m:
            val = {"n": int(m.group(1)), "P": float(m.group(3)), "R": float(m.group(4)), "map50": float(m.group(5)), "map5095": float(m.group(6))}; break
    ep_min = (its / it_s / 60.0) if it_s else None                        # 에폭당 분(지금 속도 기준)
    def _s(t):                                                            # 'mm:ss' 또는 'h:mm:ss' → 초
        try:
            ps = [int(x) for x in t.split(":")]; return sum(v * 60 ** i for i, v in enumerate(reversed(ps)))
        except Exception:
            return 0
    remain_s = _s(eta) + (eps - ep) * (ep_min or 0) * 60                  # 이 에폭 남은 것 + 남은 에폭(검증 시간은 안 넣어 조금 이르게 나온다)
    finish = time.strftime("%m-%d %H:%M", time.gmtime(time.time() + 9 * 3600 + remain_s)) if ep_min else None
    return {"name": name, "epoch": ep, "epochs": eps, "pct": int(pct), "it": it, "its": its, "it_s": round(it_s, 2), "elapsed": used, "eta": eta,
            "mem": mem, "val": val, "epoch_min": round(ep_min, 1) if ep_min else None, "remain_h": round(remain_s / 3600, 1), "finish_kst": finish}



def push_labels(dry=True):
    """이 장비와 서버의 라벨 저장소를 양쪽으로 맞춘다. 겹치는 값은 이 장비가 이긴다.

    오가는 것은 손라벨·자동라벨 뿐이다(수 MB). 영상은 보내지 않는다.
      1) 이 장비 -> 서버 : 저쪽에서 merge_labels.py --take-incoming (들어온 값 = 이 장비 값이 이긴다)
      2) 서버 -> 이 장비 : 이쪽에서 merge_labels.py (플래그 없음 = 제자리 값 = 이 장비 값을 지킨다)
    두 번 다 '없는 것만 넣고 있는 것은 지우지 않는' 규칙이라, 끝나면 양쪽이 합집합이 되고
    겹친 자리는 이 장비 값으로 같아진다. 어느 쪽에서 시작하든 결과가 같다.
    """
    import subprocess
    tgt = os.environ.get("LABEL_PUSH_TARGET", "").strip()
    if not tgt:
        return {"ok": False, "err": "LABEL_PUSH_TARGET 이 없습니다(이 장비는 보내는 쪽이 아닙니다)."}
    try:
        user_host, port, root = tgt.split(":", 2)
    except ValueError:
        return {"ok": False, "err": f"LABEL_PUSH_TARGET 형식이 잘못됐습니다: {tgt}"}
    key = os.environ.get("LABEL_PUSH_KEY", "").strip()
    # -F /dev/null: 이 장비의 ssh 설정을 읽지 않는다. 컨테이너는 root 로 도는데 마운트한
    # ~/.ssh 는 다른 사용자 소유라 ssh 가 "Bad owner or permissions" 로 거부한다.
    ssh = ["ssh", "-p", port, "-F", "/dev/null",
           "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR"]
    if key:
        ssh += ["-i", key]
    # _backup 은 합치기가 읽지 않는다. 빼지 않으면 스냅샷이 쌓일수록 전송만 무거워진다.
    rs = ["rsync", "-a", "-s", "--no-motd", "--exclude", "_backup", "--exclude", "*.tmp*",
          "-e", " ".join(ssh)]

    t0 = int(time.time())
    stage = f"/tmp/label_push_{t0}"            # 서버에 올려 둘 곳
    back = Path(f"/tmp/label_pull_{t0}")       # 서버에서 받아 둘 곳(이 장비)
    src = G / "data/학습데이터"
    subs = [s for s in ("손라벨", "자동라벨") if (src / s).is_dir()]
    try:
        # ---- 1) 이 장비 -> 서버. 겹치면 이 장비 값으로 덮는다 ----
        subprocess.run(ssh + [user_host, f"mkdir -p {stage}"], check=True, capture_output=True, timeout=60)
        for sub in subs:
            r = subprocess.run(rs + [str(src / sub), f"{user_host}:{stage}/"],
                               capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                return {"ok": False, "err": f"보내기 실패({sub}): {(r.stderr or '')[-300:]}"}
        cmd = (f"cd {root} && .venv/bin/python scripts/merge_labels.py {stage} --take-incoming"
               + (" --dry" if dry else ""))
        r1 = subprocess.run(ssh + [user_host, cmd], capture_output=True, text=True, timeout=1800)
        out1 = ((r1.stdout or "") + (r1.stderr or "")).strip()
        subprocess.run(ssh + [user_host, f"rm -rf {stage}"], capture_output=True, timeout=60)

        # ---- 2) 서버 -> 이 장비. 서버에만 있는 것을 받되 겹치면 이 장비 값을 지킨다 ----
        back.mkdir(parents=True, exist_ok=True)
        for sub in subs:
            r = subprocess.run(rs + [f"{user_host}:{root}/data/학습데이터/{sub}", f"{back}/"],
                               capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                return {"ok": False, "err": f"받기 실패({sub}): {(r.stderr or '')[-300:]}"}
        r2 = subprocess.run(["python3", str(G / "scripts/merge_labels.py"), str(back)]
                            + (["--dry"] if dry else []),
                            capture_output=True, text=True, timeout=1800)
        out2 = ((r2.stdout or "") + (r2.stderr or "")).strip()
        shutil.rmtree(back, ignore_errors=True)

        nl = chr(10)                      # f-string 안에 역슬래시를 두지 않으려고 줄바꿈을 값으로 만든다
        log = nl.join(["[이 장비 → 서버]  겹치면 이 장비 값으로 덮음",
                       out1 or "(보낼 것 없음)", "",
                       "[서버 → 이 장비]  겹치면 이 장비 값 유지",
                       out2 or "(받을 것 없음)"])
        return {"ok": r1.returncode == 0 and r2.returncode == 0, "dry": dry, "log": log[-4000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "err": "시간 초과"}
    except subprocess.CalledProcessError as e:
        # 거의 항상 ssh 키 문제다. 무엇을 해야 하는지 적어 준다.
        detail = (e.stderr or b"").decode("utf-8", "replace")[-200:] if e.stderr else str(e)
        return {"ok": False, "err": chr(10).join([
            f"서버에 접속하지 못했습니다({user_host}:{port}).",
            "이 장비의 공개키가 서버에 등록돼 있어야 합니다.",
            f"  쓰는 키: {key or "(기본 키)"}",
            f"자세한 내용: {detail}"])}
    except Exception as e:
        return {"ok": False, "err": f"{e!r}"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_error(self, code, message=None, explain=None):
        # 상태줄은 latin-1 이라 한글 사유를 넣으면 UnicodeEncodeError 로 응답 없이 끊긴다(2026-09-28, 검수 탭 404).
        # 한글 사유는 본문(explain)으로 보낸다. 호출하는 곳은 그대로 둔다
        if message and not message.isascii():
            message, explain = None, (message if explain is None else message + " · " + explain)
        super().send_error(code, message, explain)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionError, OSError):
            self.close_connection = True

    def _bytes(self, data, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try: self.wfile.write(data)
        except OSError: pass

    def _stream(self, path, ctype):
        size = path.stat().st_size
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d+)-(\d*)", rng) if rng else None
        if rng and not m:
            rng = None                                   # 접미 범위(bytes=-N) 등은 지원 안 함 → 전체 전송
        if rng:
            start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size-1
            if start >= size:
                self.send_error(416); return
            end = min(end, size-1); length = end-start+1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            start, length = 0, size
            self.send_response(200)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")   # no-cache 는 검증자가 없으면 브라우저가 그냥 재사용한다. 화면 고친 게 안 보이던 원인
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Type", ctype)
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start); left = length
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk: break
                try: self.wfile.write(chunk)
                except OSError: return
                left -= len(chunk)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/api/push_labels":       # 이 장비와 서버의 라벨을 양쪽으로 맞춘다(겹치면 이 장비 값이 이긴다)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            dry = (q.get("dry") or ["1"])[0] != "0"
            self._bytes(json.dumps(push_labels(dry), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/refresh_cache":            # 데이터 폴더 바뀐 뒤 서버 재시작 대신 이걸 누른다
            clear_caches(); sources()
            self._bytes(json.dumps({"ok": True, "sources": len(sources())}).encode(), "application/json; charset=utf-8"); return
        if p == "/api/sam2_mask":            # 포함/제외 점들로 마스크+박스(실험실 탭 조작)
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                box, poly, sc = sam2_mask_pts(b["clip"], float(b["t"]), b.get("pts") or [], b.get("box"))
                self._bytes(json.dumps({"box": box, "poly": poly, "score": round(sc, 3)}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"box": None, "poly": None, "score": 0, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_propagate_start":  # 전파를 큐에 넣는다 → 작업 id. 진행은 GET /api/sam2_jobs?clip= 로 본다
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                a = b.get("a"); bb = b.get("b")
                jid = prop_job_start(b["clip"], b.get("seeds") or [], None if a is None else float(a), None if bb is None else float(bb),
                                     float(b.get("step", 0.5)), b.get("mode") or None)
                if jid is None:
                    self._bytes(json.dumps({"err": "이 클립은 이미 전파 중입니다. 끝나면 다시 누르세요"}).encode(), "application/json; charset=utf-8"); return
                    return                               # 응답 한 번만: return 없으면 {"id":null} 을 또 써서 연결이 깨지고 이후 요청 먹통
                self._bytes(json.dumps({"id": jid}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p in ("/api/train_exclude", "/api/train_fix"):   # 입력 데이터 탭: 학습 제외 · 박스 지우기 넣기 · 빼기(손라벨 저장과 같은 잠금)
            try:
                n = int(self.headers.get("Content-Length", 0))
                r = (train_exclude_write if p == "/api/train_exclude" else train_fix_write)(json.loads(self.rfile.read(n) or b"{}"))
            except Exception as e:
                r = {"ok": False, "err": f"{type(e).__name__}: {e}"}
            self._bytes(json.dumps(r, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p == "/api/history":                 # 히스토리 저장(문서 통째로, 마지막 수정 시각 대조)
            try:
                n = int(self.headers.get("Content-Length", 0))
                r = history_write(json.loads(self.rfile.read(n) or b"{}"))
            except Exception as e:
                r = {"ok": False, "err": f"{type(e).__name__}: {e}"}
            self._bytes(json.dumps(r, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p in ("/api/catmode", "/api/datasets"):   # {cat, mode|media|gt|classes|use|note ...} 저장 → datasets.yaml. 값이 null 이면 그 필드를 지운다
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                fields = {k: v for k, v in b.items() if k != "cat" and k in ("mode", "media", "gt", "classes", "use", "note")}
                with _SAVE_LOCK:
                    cur = DATASETS.set(b["cat"], **fields)
                self._bytes(json.dumps({"ok": True, "cat": b["cat"], "cfg": cur}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_cancel":           # 이 클립의 대기·진행 중 전파 취소
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                stem = Path(b["clip"]).stem; cnt = 0
                with _PROP_LOCK:
                    for jid0, st0 in _PROP_JOBS.items():
                        if st0.get("clip") == stem and st0.get("state") in ("queued", "running"):
                            st0["cancel"] = True; cnt += 1
                            if jid0 in _PROP_Q:
                                _PROP_Q.remove(jid0); st0["state"] = "done"; st0["running"] = False; st0["err"] = "cancelled"
                self._bytes(json.dumps({"ok": True, "cancelled": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_clear":            # 전파 토글 해제: 그 클립의 SAM 결과(프레임·씨앗) 전부 제거
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                cnt = sam2_store_clear(b["clip"])
                self._bytes(json.dumps({"ok": True, "dropped": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_drop":             # 검수 × : 그 프레임을 sam2 저장소에서 뺀다
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                cnt = sam2_store_drop(b["clip"], float(b["t"]))
                self._bytes(json.dumps({"ok": True, "dropped": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_drop_obj":         # 객체 삭제: 그 객체를 sam2 저장소 전 프레임에서 뺀다
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                cnt = sam2_store_drop_obj(b["clip"], int(b["obj"]))
                self._bytes(json.dumps({"ok": True, "dropped": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/clipstate":            # {clip, mark?, a?, b?, smoke?} 준 항목만 고친다. mark=base 또는 a/b=null 이면 지운다
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                stem = Path(str(b.get("clip") or "")).stem
                if not stem:
                    raise ValueError("clip 이 없다")
                with _SAVE_LOCK:
                    fl = clip_state_file()
                    d = read_json(fl, {})
                    cur = dict(d.get(stem) or {})
                    if "mark" in b:
                        m = str(b.get("mark") or "base")
                        if m not in ("base", "prop", "hand"):
                            raise ValueError("mark 는 base/prop/hand 만 된다")
                        cur.pop("mark", None) if m == "base" else cur.update(mark=m)
                    for k in ("a", "b"):
                        if k in b:
                            cur.pop(k, None) if b[k] is None else cur.update({k: float(b[k])})
                    if "smoke" in b:                 # 연기 미완 표시. mark 와 직교한다(완료면서 연기만 남은 편이 있다)
                        cur.update(smoke="todo") if str(b.get("smoke") or "") == "todo" else cur.pop("smoke", None)
                    d.pop(stem, None) if not cur else d.update({stem: cur})
                    write_json(fl, d)
                self._bytes(json.dumps({"ok": True, "state": cur}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/clearlabels":           # 학습 프레임 초기화: 클립의 손라벨 전부 삭제(백업) + SAM 저장소 비움
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                clip = Path(body["clip"]).stem
                fn = "person_labels.json" if body.get("kind") == "person" else "fire_labels.json"
                fl = data_path("data/학습데이터/손라벨/" + fn, fn)
                with _SAVE_LOCK:
                    _backup_labels(fl)
                    rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                    keep = [r for r in rows if r.get("clip") != clip]
                    removed = len(rows) - len(keep)
                    tmp = fl.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(fl)
                sam_n = sam2_store_clear(body["clip"])
                self._bytes(json.dumps({"ok": True, "hand_rows": removed, "sam_frames": sam_n}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/savelabel":
            _SAVE_LOCK.acquire()
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                fl = label_file(body.get("kind"))
                _backup_labels(fl)
                rows = read_json(fl, [])
                clip = body["clip"]
                # t 는 초. 프레임 단위로 고른 것은 소수가 된다(30fps 면 0.03 초 간격).
                # 정수 초면 정수로 남겨 기존 라벨과 같은 모양을 유지한다.
                t = round(float(body["t"]), 2)
                t = int(t) if t == int(t) else t
                # 같은 프레임(clip,t) 기존 박스는 덮어쓴다 (재저장 = 갱신)
                rows = [r for r in rows
                        if not (r.get("clip") == clip and abs(float(r.get("t", -999)) - t) < 0.01)]
                W = int(body.get("W", 1280)); Hh = int(body.get("H", 720))
                file = body.get("file", f"{clip}_{t}.png")
                # 저장 시각. 다른 장비에서 같은 프레임을 다시 그렸을 때 어느 쪽이 새것인지
                # 파일만 보고 알 수 있어야 한다. merge_labels.py 가 이 값으로 프레임 단위로 고른다.
                ts = int(time.time())
                src = str(body.get("src") or "").replace("\\", "/") or None
                ev = {"eval": True} if body.get("eval") else {}        # 채점 전용 카테고리(검증·채점·배포)의 라벨: 학습셋 빌더가 뺀다
                for b in body.get("boxes", []):
                    cls, x, y, w, h = b[:5]
                    obj = int(b[5]) if len(b) > 5 and b[5] is not None else None   # 객체 번호(전파 박스를 손라벨로 고쳐도 정체성 유지). 없으면 안 쓴다
                    rows.append({"file": file, "clip": clip, "src": src, "t": t, "cls": int(cls),
                                 "x": round(float(x), 5), "y": round(float(y), 5),
                                 "w": round(float(w), 5), "h": round(float(h), 5),
                                 "W": W, "H": Hh, "crop": [0, 0, W, Hh], "ts": ts,
                                 **ev, **({"obj": obj} if obj is not None else {})})
                if not body.get("boxes") and not body.get("clear"):
                    # 박스 0개로 저장(사람이 다 지움) = '검토했고 객체 없음' 마커(사람·화재 공통). 이래야 다시 DINO 프리필 안 된다. clear=true 면 기록만 지운다(되돌리기)
                    rows.append({"file": file, "clip": clip, "src": src, "t": t, "cls": -1,
                                 "x": 0, "y": 0, "w": 0, "h": 0, "W": W, "H": Hh, "crop": [0, 0, W, Hh], "ts": ts})
                write_json(fl, rows)
                try:
                    _sam2_store_drop_raw(clip, t)                 # 손라벨이 SAM 을 대신: 이 프레임의 전파 결과는 저장소에서 뺀다
                except Exception:
                    pass
                self._bytes(json.dumps({"ok": True, "total": len(rows), "labels": rows}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
            finally:
                _SAVE_LOCK.release()
            return
        self.send_error(404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            self._stream(HERE/"dashboard.html", "text/html; charset=utf-8"); return
        if p.startswith("/js/") and p.endswith(".js") and "/" not in p[4:] and ".." not in p:   # 대시보드 모듈(core·review·data·editor·main)
            self._stream(HERE/"js"/p[4:], "application/javascript; charset=utf-8"); return
        if p == "/api/meta":
            f = HERE/"dash_meta.json"
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404, "dash_meta.json 없음"); return
        if p == "/api/dataset":
            f = HERE/"dataset_meta.json"
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404, "dataset_meta.json 없음"); return
        if p == "/api/labels":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            f = label_file((q.get("kind") or [""])[0])
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self._bytes(b"[]", "application/json; charset=utf-8")
            return
        if p == "/api/catmode":               # 카테고리별 라벨 모드 = datasets.yaml 의 mode (호환용)
            self._bytes(json.dumps({c: v.get("mode") for c, v in DATASETS.all().items()}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/datasets":              # 데이터 규격 전체(카테고리별 mode·media·gt·classes·use·note). 없는 카테고리는 훑어서 채운다
            cats = [d.name for d in RAW.iterdir() if d.is_dir()] if RAW.is_dir() else []
            out = {c: DATASETS.get(c) for c in sorted(set(cats) | set(DATASETS.all()))}
            self._bytes(json.dumps(out, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/pushinfo":              # 버튼을 보일지 여부(보내는 쪽에서만 보인다)
            t = os.environ.get("LABEL_PUSH_TARGET", "").strip()
            self._bytes(json.dumps({"enabled": bool(t), "target": t.split(":")[0] if t else ""},
                                   ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/config":                # 클라이언트가 알아야 하는 서버 기본값
            self._bytes(json.dumps({"prop_default": PROP_DEFAULT_MODE, "prop_thr": PROP_THR}).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2_jobs":            # 전파 작업 상태(클립별 또는 전체)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            stem = Path((q.get("clip") or [""])[0]).stem or None
            self._bytes(json.dumps(prop_jobs_view(stem)).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/gtlabel":              # 정답라벨(복사본) {frames, points, events, actions, meta}. 없으면 원본 정답에서 만든다(원본은 읽기만)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                d = gt_of((q.get("clip") or [""])[0])
            except Exception as e:
                d = {"frames": {}, "points": {}, "events": [], "actions": {}, "err": str(e)}
            self._bytes(json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/clipstates":           # 클립별 상태 전체 {stem: {mark,a,b,smoke}} (목록 표시·구간 복원용)
            self._bytes(json.dumps(read_json(clip_state_file(), {}), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8")
            return
        if p == "/api/sam2frames":           # 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지용)
            out = {}
            if SAM2_DIR.exists():
                for fj in SAM2_DIR.glob("*.json"):
                    ts = sorted(float(k) for k, v in (read_json(fj, {}).get("frames") or {}).items() if v)
                    if ts:
                        out[fj.stem] = ts
            self._bytes(json.dumps(out).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2label":            # SAM 전파 결과 저장소(클립 전체) {frames: {t: {obj: [x,y,w,h]}}, polys: {t: {obj: 윤곽선}}, seeds}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._bytes(json.dumps(_sam2_load((q.get("clip") or [""])[0]), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sources":
            self._bytes(json.dumps(sources(), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/raw":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try: lim = max(min(int((q.get("limit") or ["600"])[0]), 3000), 1)
            except ValueError: lim = 600
            got = raw_items((q.get("src") or [""])[0], lim)
            if got is None:
                self.send_error(404, "category not found"); return
            self._bytes(json.dumps(got, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/clipconds":            # 클립별 촬영 조건(야간·눈·비·안개) — 목록 필터용
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._bytes(json.dumps(clip_conds((q.get("src") or [""])[0]), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8")
            return
        if p == "/api/clips":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clips = clips_of((q.get("src") or [""])[0])
            self._bytes(json.dumps(clips, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/bench":               # 추론 속도 측정(.pt|ONNX x CPU|GPU). dumps/bench_all.json
            f = G / "dumps/bench_all.json"
            self._bytes(f.read_bytes() if f.is_file() else b"{}",
                        "application/json; charset=utf-8"); return
        if p in ("/api/review_models", "/api/review_summary", "/api/review_clip"):   # 영상 검수: 저장된 값만(추론 없음)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            g = lambda k: (q.get(k) or [""])[0]
            if p == "/api/review_models":
                body = review_models(g("item"))
            elif p == "/api/review_summary":
                body = review_summary(g("key"), g("item"))
            else:
                f = review_clip_path(g("key"), g("item"), g("clip"))
                if f is None:
                    self.send_error(404, "저장된 결과 없음"); return
                self._stream(f, "application/json; charset=utf-8"); return
            if body is None:
                self.send_error(404, "저장된 결과 없음"); return
            self._bytes(json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p == "/api/boxmodels":           # 오버레이에 쓸 수 있는 학습 모델 목록(채점셋 mAP 순)
            self._bytes(json.dumps(box_models(), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/boxdump":             # 실험별 박스 덤프. 없으면 생성 상태만 돌려준다
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            exp = (q.get("exp") or [""])[0]; clip = (q.get("clip") or [""])[0]
            rows = box_dump_read(exp, clip) if (exp and clip) else None
            if rows is not None:
                self._bytes(json.dumps({"state": "done", "rows": rows}).encode(),
                            "application/json; charset=utf-8"); return
            st = box_state(exp, clip)
            body = {"state": st}
            if st == "run":                      # 도는 중이면 지금까지 나온 것과 진행률을 같이 준다
                prows, pct = box_dump_partial(exp, clip)
                if prows:
                    body["rows"] = prows
                if pct is not None:
                    body["pct"] = pct
            self._bytes(json.dumps(body, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/boxdump_start":       # 덤프 생성 시작(백그라운드 추론)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            exp = (q.get("exp") or [""])[0]; clip = (q.get("clip") or [""])[0]
            if not exp or not clip:
                self.send_error(400, "exp/clip required"); return
            self._bytes(json.dumps({"state": box_dump_start(exp, clip)}, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/clipinfo":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            info = clip_info((q.get("clip") or [""])[0])
            if not info:
                self.send_error(404, "clip not found"); return
            self._bytes(json.dumps(info).encode(), "application/json; charset=utf-8"); return
        if p == "/api/warmframes":           # 격자를 열기 전에 필요한 프레임을 한 번에 캐시로
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clip = (q.get("clip") or [""])[0]
            w = int((q.get("w") or ["0"])[0])
            try:
                ts = [float(x) for x in (q.get("ts") or [""])[0].split(",") if x]
            except Exception:
                ts = []
            n = 0
            try:
                n = warm_frames(clip, ts, w)
            except Exception:
                pass
            self._bytes(json.dumps({"warmed": n, "total": len(ts)}).encode(),
                        "application/json; charset=utf-8")
            return
        if p == "/frameat":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try: sec = float((q.get("t") or ["0"])[0])
            except ValueError: sec = 0.0
            try: w = int(float((q.get("w") or ["0"])[0]))
            except ValueError: w = 0
            data = read_frame((q.get("clip") or [""])[0], sec, max(min(w, 4096), 0))
            if data is None:
                self.send_error(404, "frame not found"); return
            self._bytes(data, "image/jpeg"); return
        m = re.match(r"/dsimg/(.+)$", p)
        if m:
            ip = G/urllib.parse.unquote(m.group(1))
            if not ip.exists() and "/images/train/" in ip.as_posix():
                ip = Path(ip.as_posix().replace("/images/train/", "/images/"))   # train 하위 폴더 없이 images/ 에 바로 있는 세트
            if ip.exists() and WS in ip.resolve().parents:
                ext = ip.suffix.lower()
                ct = "image/png" if ext == ".png" else "image/jpeg"
                self._stream(ip, ct); return
            self.send_error(404); return
        if p == "/api/queue":                    # 실험 러너 상태(결과탭 상단). 실행중 = 실제 학습 프로세스(exp_queue.py _one <큐> <이름>), 로그=runner.log 끝
            running = []
            try:
                import subprocess as _sp
                ps = _sp.run(["pgrep", "-af", "exp_queue.py _"], capture_output=True, text=True, timeout=5).stdout
                for line in ps.splitlines():
                    w = line.split()
                    for i, x in enumerate(w):              # '_one/_score 다음이 큐 파일, 그 다음이 실험 이름' 위치에서 읽는다
                        if x.endswith("exp_queue.py") and i + 3 < len(w) and w[i + 1] in ("_one", "_score"):
                            running.append(w[i + 3]); break   # _score = 떼어 돌리는 채점(2026-09-18). 단계는 아래서 파일로 가른다
            except Exception:
                pass
            try:                                       # 부모(_one)가 죽고 학습만 살아남은 고아도 실행중으로 본다.
                ps = _sp.run(["pgrep", "-af", "model.py train"], capture_output=True, text=True, timeout=5).stdout
                for line in ps.splitlines():           # _exp/<실험명>/data.yaml 로 이름을 알아본다(exp_queue.running_elsewhere 와 같은 방법)
                    for x in line.split():
                        if "/_exp/" in x:
                            seg = x.split("/_exp/", 1)[1].split("/", 1)[0]
                            if seg:
                                running.append(seg)
            except Exception:
                pass
            q = {"running": sorted(set(running)), "log": []}
            q["jobs"] = [j for j in (train_progress(n) for n in q["running"]) if j]   # 잡별 학습 진행(에폭·속도·mAP·예상 종료)
            # 학습이 끝난 뒤 단계: mAP 검증 -> KISA 채점 -> score.txt. 화면에서 멈춘 것처럼 보이지 않게 적는다.
            for j in q["jobs"]:
                nm = j.get("name")
                if not nm:
                    continue
                rd = G / "results" / nm
                if (rd / "score.txt").is_file():
                    j["phase"] = "끝"
                elif j.get("epoch") and j.get("epochs") and j["epoch"] >= j["epochs"]:
                    j["phase"] = "KISA 채점 중" if (rd / "eval_map.json").is_file() else "mAP 검증 중"
                else:
                    j["phase"] = "학습 중"
                if j["phase"] != "학습 중":
                    j["mem"] = None        # 끝난 잡의 GPU 칸은 비운다(로그에서 긁은 유령 값이라 실제와 다르다)
            # 대기 목록: 큐 yaml 에서 score.txt 가 없고 지금 돌지도 않는 것(러너가 집는 순서 그대로)
            try:
                import yaml as _yaml
                wait = []
                live = set()                               # 러너가 실제로 읽고 있는 큐 파일만 본다
                try:
                    o = _sp.run(["pgrep", "-af", "exp_queue.py"], capture_output=True, text=True, timeout=5).stdout
                    for ln in o.splitlines():
                        for tok in ln.split():
                            if tok.endswith(".yaml"):
                                live.add(Path(tok).name)
                except Exception:
                    pass
                for qf in sorted((G / "configs").glob("queue*.yaml")):
                    if live and qf.name not in live:
                        continue                           # 집어갈 러너가 없으면 대기가 아니다
                    try:
                        d = _yaml.safe_load(qf.read_text(encoding="utf-8")) or {}
                    except Exception:
                        continue
                    for e in d.get("experiments") or []:
                        nm = e.get("name")
                        if not nm or nm in q["running"]:
                            continue
                        if (G / "results" / nm / "score.txt").is_file():
                            continue                      # 끝났거나 취소 표시된 것
                        wait.append({"name": nm, "item": e.get("item"), "queue": qf.name,
                                     "imgsz": (e.get("train") or {}).get("imgsz"),
                                     "batch": (e.get("train") or {}).get("batch")})
                q["waiting"] = wait
            except Exception:
                q["waiting"] = []
            # GPU 여유: 자리가 남는데 큐가 비어 있으면 화면에서 바로 보이게
            try:
                import subprocess as _sp2
                o = _sp2.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
                u, t, ut = [int(x.strip()) for x in o.strip().splitlines()[0].split(",")]
                q["gpu"] = {"used_mib": u, "total_mib": t, "free_mib": t - u, "util": ut}
            except Exception:
                q["gpu"] = None
            try:
                import subprocess as _sp3
                o = _sp3.run(["pgrep", "-af", "exp_queue.py"], capture_output=True, text=True, timeout=5).stdout
                n = 0
                for ln in o.splitlines():
                    w = ln.split()
                    if len(w) < 3 or "python" not in w[1]:
                        continue                       # 첫 토큰이 python 인 것만(러너를 띄운 bash -c 줄을 뺀다)
                    for i, x in enumerate(w):
                        if x.endswith("exp_queue.py") and i + 1 < len(w) and w[i + 1] == "run":
                            n += 1; break
                q["runners"] = n
            except Exception:
                q["runners"] = None
            try:
                q["log"] = (G / "logs/queue/runner.log").read_text(encoding="utf-8", errors="ignore").splitlines()[-25:]
            except Exception:
                pass
            self._bytes(json.dumps(q, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p == "/api/history":                   # 히스토리 탭(2026-09-30) 원본 configs/history.yaml
            try:
                body = history_read()
            except Exception as ex:
                body = {"error": f"{type(ex).__name__}: {ex}"}
            self._bytes(json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p in ("/api/train_exclude", "/api/train_fix"):   # 입력 데이터 탭 학습 제외 · 라벨 고침 목록(POST 로 고친다)
            fl = train_exclude_file() if p == "/api/train_exclude" else train_fix_file()
            self._bytes(json.dumps(read_json(fl, {"items": []}), ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p in ("/api/tv_exps", "/api/tv_set", "/api/tv_thumb", "/api/tv_summary", "/api/data_modules"):   # 학습 데이터 보기(2026-10-01) · 입력 데이터 탭(10-02). 읽기만. 계산은 dash_v2/trainview.py
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            g = lambda k, d="": (q.get(k) or [d])[0]
            try:
                import trainview as _TV
                if p == "/api/tv_thumb":
                    data = _TV.thumb(g("p"), max(64, min(int(float(g("w", "320"))), 1600)))
                    self._bytes(data, "image/jpeg") if data else self.send_error(404); return
                body = (_TV.exps() if p == "/api/tv_exps" else _TV.summaries() if p == "/api/tv_summary" else _TV.data_modules() if p == "/api/data_modules"   # data_modules = configs/data_modules.yaml 그대로
                        else _TV.set_page(g("name"), g("flag", "sus"), max(0, int(g("offset", "0"))), max(1, min(int(g("limit", "60")), 200))))
            except Exception as ex:
                body = {"error": f"{type(ex).__name__}: {ex}"}
            self._bytes(json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p == "/api/result_blocks":             # 결과 탭(2026-09-29 재설계): 새 데이터 판 비교 블록. 계산은 dash_v2/results_newdata.py
            try:
                import results_newdata as _RN
                body = _RN.build()
            except Exception as ex:
                body = {"error": f"{type(ex).__name__}: {ex}"}
            self._bytes(json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p == "/api/results":
            out = []
            # 항목 → 그 항목이 쓰는 가중치의 계보(results/MODELS.json). 라이브 SA 채점 로그에는
            # meta 가 없어 결과 탭의 해상도·입력데이터·기법 열이 비는데, 그 값이 여기 있다.
            _mdl = {}
            try:
                _mj = json.loads((G / "results/MODELS.json").read_text(encoding="utf-8"))
                for _w, _e in (_mj.get("models") or {}).items():
                    _ds = _e.get("dataset") or {}
                    for _it in (_e.get("used_by") or []):
                        _mdl.setdefault(_it, []).append((_w, _e, _ds))
            except Exception as _ex:
                print("[results] MODELS.json 못 읽음:", _ex, flush=True)

            def _meta_from_models(item, cfg_line):
                """항목이 쓰는 가중치로 meta 를 만든다. 없으면 None."""
                ms = _mdl.get(item) or []
                if not ms:
                    return None
                # 검출 모델을 대표로 삼는다(쓰러짐은 pose + SeqNet 두 개라 앞의 것)
                w, e, ds = ms[0]
                base, extras = None, []
                for c in (ds.get("composition") or []):
                    nm = c.get("source", "")
                    if base is None:
                        base = nm
                    else:
                        extras.append(nm)
                t = dict(e.get("train") or {})
                # 실행마다 다를 수 있는 해상도는 로그의 [설정] 줄을 우선한다
                if cfg_line:
                    m_ = re.search(r"해상도=(\d+)", cfg_line)
                    if m_:
                        t["imgsz"] = int(m_.group(1))
                # 모델 열은 아키텍처로 통일한다(person_v3.pt 도 yolo11s 로 학습한 것).
                # 무슨 데이터로 학습했는지는 입력데이터 열이 말한다.
                arch = (e.get("base_model") or w).replace(".pt", "")
                return {"model": arch, "base": base, "extras": extras,
                        "n_train": ds.get("total"), "train": t,
                        "oversample": None, "extra": None, "status": None,
                        "started": None, "ended": None,
                        "eval_map": {"map50": e.get("val_map50")} if e.get("val_map50") else None,
                        "bench": None,
                        "_from_models": True,
                        "_dataset_status": ds.get("status")}
            rdir = G / "results"
            pat = re.compile(r"^\s*(.+?)\s+→\s+([0-9.]+)\s+\(정검 (\d+) 미검 (\d+) 오검 (\d+)\)", re.M)
            files = sorted(rdir.glob("*.txt")) + sorted(rdir.glob("*/score.txt"))   # 구(평면 txt) + 신(results/<exp>/score.txt)
            for f in files:
                try:
                    txt = f.read_text(errors="ignore")
                except Exception:
                    continue
                _meta = {}
                if f.name == "score.txt":                       # 새 레이아웃: 실험명=폴더명, item 은 meta.json
                    try: _meta = json.loads((f.parent / "meta.json").read_text(encoding="utf-8"))
                    except Exception: _meta = {}
                    try: _meta["bench"] = json.loads((f.parent / "bench.json").read_text(encoding="utf-8"))        # 이 실험의 추론 속도
                    except Exception: pass
                    try: _meta["eval_map"] = json.loads((f.parent / "eval_map.json").read_text(encoding="utf-8"))   # 채점 전용 검증셋 mAP
                    except Exception: pass
                rows = []
                for m in pat.finditer(txt):
                    rows.append({"rule": m.group(1).strip(), "score": float(m.group(2)),
                                 "tp": int(m.group(3)), "fn": int(m.group(4)), "fp": int(m.group(5))})
                if not rows:
                    continue
                _clips = {m.group(1): m.group(2) for m in re.finditer(r"^\s*클립 (\S+): (\S+)", txt, re.M)}   # score_kisa 클립별 판정
                best = max(rows, key=lambda r: r["score"])
                _oldrows = [r for r in rows if not r["rule"].startswith("신규칙")]   # 구 규칙만의 최고(신규칙과 나란히)
                _score_old = max(_oldrows, key=lambda r: r["score"])["score"] if _oldrows else None
                _stem = f.parent.name if f.name == "score.txt" else f.stem
                _s = _stem.lower()
                if _meta.get("item"):
                    _item = _meta["item"]
                elif "intrusion" in _s or "\uce68\uc785" in _s:      # 침입
                    _item = "\uce68\uc785"
                elif "loiter" in _s or "roam" in _s or "\ubc30\ud68c" in _s:   # 배회
                    _item = "\ubc30\ud68c"
                elif "fall" in _s or "faint" in _s or "collapse" in _s or "\uc4f0\ub7ec" in _s:  # 쓰러짐
                    _item = "\uc4f0\ub7ec\uc9d0"
                else:
                    _item = "\ubc29\ud654"                       # 방화(기본)
                # 사람 검출 모델 실험은 '규칙' 자리에 항목(intrusion/loiter)이 온다.
                # 항목별로 따로 올려야 침입·배회 표에서 보인다.
                if _item == "사람":
                    _ITEM_OF = {"intrusion": "침입", "loiter": "배회", "loitering": "배회",
                                "falldown": "쓰러짐", "fall": "쓰러짐", "fire": "방화"}
                    for _r in rows:
                        _sub = _ITEM_OF.get(_r["rule"].strip().lower())
                        if not _sub:
                            continue
                        out.append({"name": _stem, "score": _r["score"], "rule": "고정 규칙",
                                    "tp": _r["tp"], "fn": _r["fn"], "fp": _r["fp"],
                                    "item": _sub, "score_old": None,
                                    "meta": {k: _meta.get(k) for k in ("model", "base", "extras", "extra", "status",
                                                                       "n_train", "train", "oversample", "started",
                                                                       "ended", "eval_map", "bench")},
                                    "clips": _clips, "n": 1, "mtime": int(f.stat().st_mtime),
                                    "rules": [dict(_r, rule="고정 규칙")]})
                    continue
                out.append({"name": _stem, "score": best["score"], "rule": best["rule"],
                            "tp": best["tp"], "fn": best["fn"], "fp": best["fp"], "item": _item, "score_old": _score_old,
                            "meta": {k: _meta.get(k) for k in ("model", "base", "extras", "extra", "status", "n_train", "train", "oversample", "started", "ended", "eval_map", "bench")}, "clips": _clips,
                            "n": len(rows), "mtime": int(f.stat().st_mtime), "rules": rows})
            # ---- 라이브 SA 생성기 채점 로그(logs/queue/val_*.log): 침입·배회·쓰러짐(·방화) 항목별 점수 + 클립별 판정 ----
            ITEM_OF = {"fire": "방화", "intrusion": "침입", "loitering": "배회", "loiter": "배회", "falldown": "쓰러짐", "fall": "쓰러짐"}
            for f in sorted((G / "logs/queue").glob("val_*.log")):
                try:
                    txt = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                last = None
                for last in re.finditer(r"^\[(\w+)\] 정검 (\d+) 미검 (\d+) 오검 (\d+) → 점수 ([0-9.]+)(.*)$", txt, re.M):
                    pass
                if not last:
                    continue
                _clips = {c.group(1): c.group(2) for c in re.finditer(r"^\s*클립 (\S+): (\S+)", txt, re.M)}
                # 실행 설정 한 줄(kisa_items.py 가 첫 줄에 찍는다). 옛 로그에는 없다.
                _cfg = re.search(r"^\[설정\] (.+)$", txt, re.M)
                st = "합격" if "합격" in last.group(6) else last.group(6).strip(" ()") or ""
                row = {"rule": "라이브 SA 생성기(kisa_items)", "score": float(last.group(5)), "tp": int(last.group(2)), "fn": int(last.group(3)), "fp": int(last.group(4))}
                _it2 = ITEM_OF.get(last.group(1), last.group(1))
                _mm = {"kind": "live_sa", "status": st, "note": f"logs/queue/{f.name}",
                       "config": _cfg.group(1) if _cfg else None}
                _fill = _meta_from_models(_it2, _mm["config"])
                if _fill:
                    _mm.update(_fill)          # 해상도·입력데이터·기법 열이 읽는 자리를 채운다
                out.append({"name": f.stem, "score": row["score"], "rule": row["rule"], "tp": row["tp"], "fn": row["fn"], "fp": row["fp"],
                            "item": _it2, "score_old": None,
                            "meta": _mm, "clips": _clips,
                            "n": 1, "mtime": int(f.stat().st_mtime), "rules": [row]})
            # 2026-09-15: ALL_RESULTS.json 별도 읽기를 없앴다. 그 안의 규칙 비교는
            # results/<항목>_규칙비교_20260907/score.txt 로 펼쳐 다른 실험과 같은 경로로 읽힌다.
            # ---- 합쳐 만든 학습셋은 구성으로 펼친다 ----
            # base 가 data/학습데이터/<이름>/ 이면 그 meta.json 의 stats 가 원본별 장수를 안다.
            # 이름만 보여주면 무엇이 몇 장 들어갔는지 알 수 없다(방화는 원본 이름이 직접 들어가 보인다).
            _dscache = {}

            def _expand(name):
                if name in _dscache:
                    return _dscache[name]
                out_ = None
                mf = G / "data/학습데이터" / str(name) / "meta.json"
                if mf.is_file():
                    try:
                        dm = json.loads(mf.read_text(encoding="utf-8"))
                        lab = {"이미지": "", "영상프레임": "영상 "}
                        comp = []
                        for k, v in (dm.get("stats") or {}).items():
                            if not isinstance(v, int) or k.startswith("제외"):
                                continue          # 제외 항목은 안 들어간 것이다
                            p = k.split(":")
                            if p[0] == "이미지" and len(p) >= 2:
                                comp.append((p[1], v))                    # 원본 데이터셋 이름
                            elif p[0] == "영상프레임" and len(p) >= 2:
                                comp.append(("영상프레임 " + p[1], v))     # hand · sam
                            else:
                                comp.append((k, v))
                        comp.sort(key=lambda x: -x[1])
                        out_ = {"comp": comp, "train": dm.get("train"), "val": dm.get("val")}
                    except Exception:
                        out_ = None
                _dscache[name] = out_
                return out_

            for _r in out:
                _m = _r.get("meta") or {}
                if not _m.get("base") or _m.get("extras"):
                    continue                      # 이미 원본 이름이 들어 있으면 그대로
                _e = _expand(_m["base"])
                if not _e or not _e["comp"]:
                    continue
                _m["base"] = f"{_e['comp'][0][0]} {_e['comp'][0][1]:,}"
                _m["extras"] = [f"{n} {v:,}" for n, v in _e["comp"][1:]]
                if _e["train"]:
                    _m["n_train"] = _e["train"]   # 무엇을 센 값인지 분명한 쪽으로

            # ---- 같은 가중치로 돌린 실행들을 한 줄로 접는다 ----
            # 모델별 성능 = 모델이 다른 것 / 규칙 스윕 = 같은 모델에 규칙만 다른 것.
            # 방화(러너)는 한 실험 안에서 이미 스윕하므로 건드리지 않는다.
            _fold = {}
            _keep = []
            for _r in out:
                _m = _r.get("meta") or {}
                if _m.get("kind") not in ("live_sa", "archive") or not _m.get("model"):
                    _keep.append(_r)
                    continue
                _k = (_r["item"], _m["model"])
                # 이 실행이 규칙 스윕에서 어떤 줄이 될지: 사람이 읽을 이름 + 파라미터
                _lab = (_m.get("extra") or {}).get("기법") or _r["name"].replace("_20260910", "")
                _par = _r["rule"] if _r["rule"] and "라이브 SA 생성기" not in _r["rule"] else ""
                if not _par and _m.get("config"):
                    _par = " ".join(re.findall(r"해상도=\d+|임계=[\d.]+|연속창=\d+|conf=[\d.]+", _m["config"]))
                _row = {"rule": (_lab + (" · " + _par if _par else "")),
                        "score": _r["score"], "tp": _r["tp"], "fn": _r["fn"], "fp": _r["fp"]}
                if _k not in _fold:
                    _fold[_k] = _r
                    _r["rules"] = [_row]
                    _r["name"] = _m["model"]          # 접은 줄의 이름 = 아키텍처
                else:
                    _b = _fold[_k]
                    _b["rules"].append(_row)
                    if _r["score"] > _b["score"]:     # 대표는 최고 점수
                        _b.update({k: _r[k] for k in ("score", "rule", "tp", "fn", "fp", "clips")})
                        _b["meta"] = _m
                        _b["name"] = _m["model"]
                    _b["mtime"] = max(_b["mtime"], _r["mtime"])
            for _b in _fold.values():
                _b["rules"].sort(key=lambda x: -x["score"])
                _b["rule"] = _b["rules"][0]["rule"]   # 대표 규칙 = 최고 점수를 낸 것
                _b["n"] = len(_b["rules"])
                _keep.append(_b)
            out = _keep
            out.sort(key=lambda r: -r["score"])
            self._bytes(json.dumps(out).encode("utf-8"), "application/json; charset=utf-8"); return
        if p == "/api/rawlabel":                 # 이미지 원본 정답 → 우리 클래스 규약의 YOLO 줄(datasets.yaml 의 gt·classes 로 변환)
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            rel = qs.get("rel", [""])[0]
            try:
                cfg = DATASETS.get(cat_of(rel))
                d = GTA.image_gt(cfg, G, rel)
                if d is not None:
                    self._bytes(GTA.to_yolo_lines(d).encode("utf-8"), "text/plain; charset=utf-8"); return
            except Exception:
                pass
            sib = (G/rel).with_suffix(".txt")               # 1) 원본 옆 YOLO txt
            try:
                if sib.exists() and WS in sib.resolve().parents:
                    self._stream(sib, "text/plain; charset=utf-8"); return
            except Exception:
                pass
            cl = coco_labels(rel)                            # 2) 원본 COCO annotations(train/val/test 전부)
            if cl:
                self._bytes(cl.encode("utf-8"), "text/plain; charset=utf-8"); return
            lp = raw_sibling_label(rel)                      # 2.5) 라벨이 다른 트리에 있는 원본(open_coco 등)
            if lp is not None:
                self._stream(lp, "text/plain; charset=utf-8"); return
            stem = Path(rel).stem                            # 3) 변환된 학습 라벨(파일명 매칭)
            for sp in ("train", "val"):
                for cp in (G/"data/학습데이터").glob("*/labels/" + sp + "/" + stem + ".txt"):
                    try:
                        if cp.exists() and WS in cp.resolve().parents:
                            self._stream(cp, "text/plain; charset=utf-8"); return
                    except Exception:
                        pass
            self._bytes(b"", "text/plain"); return
        m = re.match(r"/dslabel/(.+\.txt)$", p)
        if m:
            lp = G/urllib.parse.unquote(m.group(1))
            if not lp.exists() and "/labels/train/" in lp.as_posix():
                lp = Path(lp.as_posix().replace("/labels/train/", "/labels/"))
            if lp.exists() and WS in lp.resolve().parents:
                self._stream(lp, "text/plain; charset=utf-8"); return
            self._bytes(b"", "text/plain"); return
        m = re.match(r"/vid/(.+\.mp4)$", p)
        if m:
            rel = urllib.parse.unquote(m.group(1)); vp = G/rel
            # 맥 하드웨어 디코더가 못 읽는 편(C00_089_0001 3:33, 오류 3)은 플레이어가 ?safe=1 로 다시 부른다.
            # 다시 인코딩한 시청용 사본(dumps/vid_safe, 같은 경로)이 있으면 그걸 준다. 채점에는 안 쓴다
            if "safe=1" in urllib.parse.urlparse(self.path).query and (G/"dumps"/"vid_safe"/rel).exists():
                vp = G/"dumps"/"vid_safe"/rel
            if vp.exists() and WS in vp.resolve().parents: self._stream(vp, "video/mp4")
            else: self.send_error(404, "video not found")
            return
        m = re.match(r"/frame/(.+\.png)$", p)
        if m:
            name = urllib.parse.unquote(m.group(1))
            fp = data_path("data/학습데이터/손라벨/full", "labelfull")/name
            if fp.exists(): self._stream(fp, "image/png"); return
            # 뽑아 둔 프레임 폴더가 없으면(지금 서버 A · B 다 없음) 손라벨 줄의 원본 영상 · 초(t)로 그 자리에서 뽑는다
            row = next((r for r in read_json(label_file("fire"), []) if r.get("file") == name and r.get("src") and r.get("t") is not None), None)
            data = read_frame(row["src"].rsplit(".", 1)[0], float(row["t"])) if row else None
            if data is None: self.send_error(404)
            else: self._bytes(data, "image/jpeg")
            return
        self.send_error(404)



def _warmup_models():
    """SAM2 이미지·비디오 모델을 미리 GPU 에 올린다(첫 요청 지연 제거). 실패해도 서버는 뜬다."""
    try:
        import torch
        from transformers.models.sam2.processing_sam2 import Sam2Processor
        from transformers.models.sam2.modeling_sam2 import Sam2Model
        global _SAM2
        if _SAM2 is None:
            dev = torch_device()
            _SAM2 = (Sam2Processor.from_pretrained(SAM2_ID), Sam2Model.from_pretrained(SAM2_ID).to(dev).eval(), dev)
    except Exception as e:
        print("[warmup] sam2 image:", e, flush=True)
    try:
        from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
        from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
        global _SAM2V
        if _SAM2V is None:
            dev = torch_device()
            _SAM2V = (Sam2VideoProcessor.from_pretrained(SAM2V_ID), Sam2VideoModel.from_pretrained(SAM2V_ID).to(dev).eval(), dev)
    except Exception as e:
        print("[warmup] sam2 video:", e, flush=True)
    print("[warmup] done", flush=True)

if __name__ == "__main__":
    threading.Thread(target=_warmup_models, daemon=True).start()
    print(f"통합 대시보드: http://localhost:{PORT}/  (ssh -L {PORT}:localhost:{PORT} 로 로컬 접속)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()

# -*- coding: utf-8 -*-
"""학습셋 빌더(규격 기반). datasets.yaml 만 보고 움직인다 — 데이터셋별 스크립트·하드코딩 없음.

한 모드(fire | person)의 학습셋을 YOLO 형식으로 만든다:
  우선순위  손라벨(사용자) > SAM 전파(사용자가 전파한 것) > 원본 정답(어댑터 + classes 매핑)
  제외      use != train 인 카테고리(eval = 채점 전용, none = 라이선스 등) · eval 표시가 붙은 손라벨 행
  영상      라벨된 시각의 프레임을 원본 mp4 에서 뽑아 jpg 로(원본은 읽기만). 이미지는 원본 파일을 가리키는 심링크(복사 안 함)
출력       data/학습데이터/trainset_<mode>_<날짜>/{images,labels}/{train,val} + train.txt/val.txt + data.yaml + meta.json
검증 분할  영상은 클립 단위, 이미지는 파일 해시로 VAL_FRAC 비율(같은 장면이 학습·검증에 섞이지 않게)

사용: python scripts/build_trainset.py fire|person [--name 이름] [--val 0.1] [--max-gt N: 카테고리당 원본 정답 이미지 상한]
"""
import sys, os, io, json, glob, hashlib, argparse, collections, time
from pathlib import Path
import cv2
import kisa_paths as KP            # 저장소 루트·배포 경로는 여기 한 곳에서만 정의한다
V = KP.V
sys.path.insert(0, str(V / "dash_v2"))
import gt_adapters as GTA

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["fire", "person"])
ap.add_argument("--name", default=None)
ap.add_argument("--val", type=float, default=0.1)
ap.add_argument("--max-gt", type=int, default=0, help="카테고리당 원본 정답 이미지 상한(0=전부)")
ap.add_argument("--neg", type=int, default=5, help="손라벨 클립당 앞/뒤 각 하드 네거티브 장수(0=끔). 상한=그 클립 양성 프레임 수")
ap.add_argument("--no-gt", action="store_true", help="원본 정답 이미지는 넣지 않는다(우리 라벨만: 손·전파·하드네거·이미지 손라벨). 오버샘플용 handset")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()

RAW = V / "data/원본데이터"
D = GTA.Datasets(V / "configs/datasets.yaml", RAW)
NAME = a.name or f"trainset_{a.mode}_{time.strftime('%Y%m%d')}"
OUT = V / "data/학습데이터" / NAME
NAMES = ["fire", "smoke"] if a.mode == "fire" else ["person"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def is_val(key):
    return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF < a.val


def yolo_line(c, b):
    return "%d %.6f %.6f %.6f %.6f" % (c, b[0] + b[2] / 2, b[1] + b[3] / 2, b[2], b[3])


items = []      # (split, image_path_or_(mp4,t), [ (cls, [x,y,w,h]) ], 출처)
stats = collections.Counter()

# ---------- 1) 손라벨(사용자) ----------
hand_kind = "person" if a.mode == "person" else "fire"
hand_rows = json.load(io.open(V / f"data/학습데이터/손라벨/{hand_kind}_labels.json", encoding="utf-8")) if (V / f"data/학습데이터/손라벨/{hand_kind}_labels.json").exists() else []
img_rows = json.load(io.open(V / "data/학습데이터/손라벨/image_labels.json", encoding="utf-8")) if (V / "data/학습데이터/손라벨/image_labels.json").exists() else []
hand_frames = collections.defaultdict(list)      # (clip_stem, t) → 박스
hand_src = {}
for r in hand_rows:
    if r.get("eval"):
        stats["제외:eval 손라벨"] += 1; continue
    key = (r["clip"], round(float(r["t"]) * 2) / 2)
    hand_src.setdefault(key, r.get("src"))
    if int(r.get("cls", -1)) >= 0:
        hand_frames[key].append((int(r["cls"]), [r["x"], r["y"], r["w"], r["h"]]))
    else:
        hand_frames.setdefault(key, [])          # 빈 라벨(검토완료) = 배경 프레임
hand_imgs = {}                                   # rel → 박스
for r in img_rows:
    rel = str(r["clip"])[4:] if str(r["clip"]).startswith("img:") else r.get("file")
    if not rel or r.get("eval"):
        continue
    parts = rel.split("/")
    if len(parts) < 3 or D.get(parts[2]).get("mode") != a.mode:   # rel = data/원본데이터/<카테고리>/...
        continue
    hand_imgs.setdefault(rel, [])
    if int(r.get("cls", -1)) >= 0:
        hand_imgs[rel].append((int(r["cls"]), [r["x"], r["y"], r["w"], r["h"]]))

# ---------- 2) SAM 전파(사용자가 전파한 것). 손라벨 프레임은 이미 빠져 있다 ----------
sam_frames = collections.defaultdict(list)
for f in glob.glob(str(V / "data/학습데이터/자동라벨/sam2/*.json")):
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except Exception:
        continue
    stem = d.get("clip") or Path(f).stem
    for k, objs in (d.get("frames") or {}).items():
        key = (stem, round(float(k) * 2) / 2)
        if key in hand_frames or not objs:
            continue
        for o, b in objs.items():
            c = (0 if int(o) == 1 else 1) if a.mode == "fire" else 0
            sam_frames[key].append((c, b))


_MP4 = None
def clip_full(stem):
    global _MP4
    if _MP4 is None:
        _MP4 = {p.stem: p for p in RAW.rglob("*.mp4")}   # mp4 색인 한 번(원본 전체를 클립마다 훑지 않게)
    return _MP4.get(stem)


# 영상 프레임(손라벨 + SAM): 카테고리 use/mode 확인
vid_cache = {}
for src_name, frames in (("hand", hand_frames), ("sam", sam_frames)):
    for (stem, t), boxes in frames.items():
        mp4 = vid_cache.get(stem)
        if mp4 is None:
            mp4 = clip_full(stem); vid_cache[stem] = mp4 or False
        if not mp4:
            stats["영상 없음"] += 1; continue
        cat = mp4.relative_to(RAW).parts[0]
        cfg = D.get(cat)
        if cfg.get("mode") != a.mode:
            stats[f"제외:모드다름({cat})"] += 1; continue
        if cfg.get("use") != "train":
            stats[f"제외:use={cfg.get('use')}({cat})"] += 1; continue
        items.append(("val" if is_val(stem) else "train", (mp4, t), boxes, src_name))
        stats[f"영상프레임:{src_name}"] += 1

# ---------- 2.5) 하드 네거티브(손라벨 클립만): 라벨 구간 앞뒤 배경을 무라벨로 ----------
NEG_STEP = 0.5                                   # 샘플 간격(초)
NEG_BUF = 10 if a.mode == "fire" else 0          # 라벨 구간에서 띄울 간격(스텝). 불연기=10프레임 버퍼(연기가 인접 프레임까지 번짐), 사람=바로 앞뒤
occ = collections.defaultdict(set)               # stem → 양성 시각(손+SAM): 버퍼·배제에 쓴다
hand_pos_n = collections.Counter()               # stem → 손라벨 양성 프레임 수(개수 상한)
for (stem, t), boxes in hand_frames.items():
    if boxes:
        occ[stem].add(t); hand_pos_n[stem] += 1
for (stem, t), boxes in sam_frames.items():
    if boxes:
        occ[stem].add(t)
if a.neg > 0:
    for stem in sorted(occ):
        if not hand_pos_n[stem]:                 # 손라벨이 있는 클립만(SAM 만 있는 건 제외)
            continue
        mp4 = vid_cache.get(stem)
        if not mp4:
            continue
        cfg = D.get(mp4.relative_to(RAW).parts[0])
        if cfg.get("mode") != a.mode or cfg.get("use") != "train":   # 채점(eval)·라이선스(none) 클립은 네거티브로도 안 쓴다(누수)
            continue
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / (fps or 30.0); cap.release()
        pos = occ[stem]; f0, f1 = min(pos), max(pos); buf = NEG_BUF * NEG_STEP
        before = [round(f0 - buf - k * NEG_STEP, 1) for k in range(1, a.neg + 1)]
        before = [t for t in before if t >= 0.5]
        after = [round(f1 + buf + k * NEG_STEP, 1) for k in range(1, a.neg + 1)]
        after = [t for t in after if t <= dur - 0.5]
        cand = [x for pair in zip(before, after) for x in pair] + before[len(after):] + after[len(before):]   # 앞뒤 번갈아(균형)
        cand = [t for t in cand if all(abs(t - q) >= NEG_STEP for q in pos)]   # 양성 근처 제외(안전)
        cand = cand[:hand_pos_n[stem]]           # 상한 = 손라벨 양성 프레임 수
        for t in cand:
            items.append(("val" if is_val(stem) else "train", (mp4, t), [], "neg"))
            stats["하드네거티브"] += 1

# ---------- 3) 이미지: 손라벨 > 원본 정답(어댑터) ----------
for cat, cfg in sorted(D.all().items()):
    cfg = D.get(cat)
    if cfg.get("mode") != a.mode or cfg.get("media") != "image" or cfg.get("use") != "train":
        continue
    n_gt = 0
    for p in sorted((RAW / cat).rglob("*")):
        if p.suffix.lower() not in IMG_EXT or "infrared" in str(p).lower() or "thermal" in str(p).lower():
            continue
        rel = str(p.relative_to(V)).replace("\\", "/")
        if rel in hand_imgs:
            boxes, src_name = hand_imgs[rel], "hand"
        else:
            if a.no_gt:
                continue                                     # --no-gt: 우리 라벨만
            if cfg.get("gt") in (None, "none"):
                continue                                     # 정답 없고 손라벨도 없는 이미지는 안 넣는다
            if a.max_gt and n_gt >= a.max_gt:
                continue
            d = GTA.image_gt(cfg, V, rel)
            if d is None:
                continue                                     # 라벨 파일 없음
            fr = (d.get("frames") or {}).get("0.0") or {}
            boxes = [(int(d["cls"][o]), b) for o, b in fr.items()]
            src_name = "gt"; n_gt += 1
        items.append(("val" if is_val(rel) else "train", p, boxes, src_name))
        stats[f"이미지:{cat}:{src_name}"] += 1

_EVAL_STEMS = {p.stem for c, cfg in D.all().items() if cfg.get("use") == "eval" for p in (RAW / c).rglob("*.mp4")}   # 채점 전용 클립: 학습·배경 어느 쪽으로도 절대 안 들어간다
_leak = [src[0].stem for sp, src, bx, sn in items if isinstance(src, tuple) and src[0].stem in _EVAL_STEMS]
assert not _leak, f"채점 전용 클립이 학습셋에 들어갔다: {sorted(set(_leak))[:5]}"
stats["채점클립 검사"] = f"누수 0 (채점 클립 {len(_EVAL_STEMS)}편 제외 확인)"
print(f"[{NAME}] 항목 {len(items):,}개"); [print(f"  {k}: {v}") for k, v in sorted(stats.items())]
if a.dry:
    sys.exit(0)

for sp in ("train", "val"):
    (OUT / "images" / sp).mkdir(parents=True, exist_ok=True); (OUT / "labels" / sp).mkdir(parents=True, exist_ok=True)
lists = {"train": [], "val": []}
caps = {}
for sp, src, boxes, src_name in items:
    if isinstance(src, tuple):                               # 영상 프레임 → jpg 추출
        mp4, t = src
        name = f"{mp4.stem}_{int(round(t * 10)):05d}"
        jp = OUT / "images" / sp / f"{name}.jpg"
        if not jp.exists():
            cap = caps.get(mp4)
            if cap is None:
                cap = caps[mp4] = cv2.VideoCapture(str(mp4))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(t * fps)), 0))
            ok, fr = cap.read()
            if not ok:
                stats["프레임 실패"] += 1; continue
            cv2.imwrite(str(jp), fr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    else:                                                    # 이미지 → 심링크(복사 안 함)
        name = f"{src.parent.parent.name}_{src.parent.name}_{src.stem}".replace(" ", "_")
        jp = OUT / "images" / sp / f"{name}{src.suffix.lower()}"
        if not jp.exists():
            os.symlink(src, jp)
    (OUT / "labels" / sp / f"{jp.stem}.txt").write_text("".join(yolo_line(c, b) + "\n" for c, b in boxes))
    lists[sp].append(str(jp))
for c in caps.values():
    c.release()
for sp in ("train", "val"):
    (OUT / f"{sp}.txt").write_text("\n".join(lists[sp]) + "\n")
(OUT / "data.yaml").write_text(f"path: {OUT}\ntrain: {OUT}/train.txt\nval: {OUT}/val.txt\nnc: {len(NAMES)}\nnames: {NAMES}\n")
meta = {"name": NAME, "mode": a.mode, "built": time.strftime("%F %T"), "train": len(lists["train"]), "val": len(lists["val"]),
        "priority": "hand > sam > gt", "excluded": "use!=train, eval rows", "stats": dict(stats), "contract": "configs/datasets.yaml"}
(OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료 → {OUT}  train {len(lists['train']):,} · val {len(lists['val']):,}")

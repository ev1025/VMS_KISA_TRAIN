# -*- coding: utf-8 -*-
"""검증셋 빌더: 채점 전용 카테고리(use: eval)의 영상에서 사람이 만든 라벨만 모아 mAP 검증셋을 만든다. 학습에 절대 넣지 않는다(검증 전용).
  포함  1) 손라벨 eval 행(cls -1 = 검토완료 → 박스 없는 배경 프레임)
        2) SAM 전파 결과(자동라벨/sam2/<stem>.json) — 채점 전용 카테고리 클립만. 손라벨 프레임이 있으면 손라벨이 우선
        3) 배경 프레임 자동 표본(--bg N): 정답 XML 의 화재 발생 시각(StartTime) 이전 [0, 시작-여유) 구간에서 N장. 정답이 '불 없음'을 보증하는 구간이라 사람이 안 쳐도 된다
  출력  data/학습데이터/evalset_<mode>/{images,labels}/ + val.txt + meta.json
  사용  python scripts/build_evalset.py fire [--name evalset_fire] [--bg 10] [--bg-margin 5]
러너(exp_queue.py)는 defaults.val_set 에 이 val.txt 경로를 주면 val_small 대신 이걸 검증셋으로 쓴다."""
import sys, io, json, argparse, collections, time
from pathlib import Path
import cv2
import kisa_paths as KP            # 저장소 루트는 여기 한 곳에서만 정의한다
V = KP.V
sys.path.insert(0, str(V / "dash_v2")); import gt_adapters as GTA
ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["fire", "person"]); ap.add_argument("--name", default=None)
ap.add_argument("--bg", type=int, default=10, help="클립마다 화재 발생 전 구간에서 뽑을 배경 프레임 수(0=안 뽑음)")
ap.add_argument("--bg-margin", type=float, default=5.0, help="발생 시각 앞 여유(초). 이 안쪽은 배경으로 안 쓴다(불씨가 보일 수 있다)")
a = ap.parse_args()
RAW = V / "data/원본데이터"; D = GTA.Datasets(V / "configs/datasets.yaml", RAW)
NAME = a.name or f"evalset_{a.mode}"; OUT = V / "data/학습데이터" / NAME
NAMES = ["fire", "smoke"] if a.mode == "fire" else ["person"]
stats = collections.Counter()


EVAL_CATS = sorted(c for c, cfg in D.all().items() if cfg.get("use") == "eval")
def _clip_mode(p):                                  # 채점 카테고리는 항목별 하위 폴더(방화/침입/배회/쓰러짐)가 섞여 있다 → 폴더 이름으로 모드
    s = str(p)
    return "fire" if "방화" in s else ("person" if any(k in s for k in ("침입", "배회", "쓰러짐")) else D.get(p.relative_to(RAW).parts[0]).get("mode"))
EVAL_MP4 = {p.stem: p for c in EVAL_CATS for p in (RAW / c).rglob("*.mp4") if _clip_mode(p) == a.mode}   # 채점 전용 카테고리 안만 한 번 훑는다


def eval_clip(stem):
    """채점 전용 카테고리의 영상이면 경로, 아니면 None."""
    mp4 = EVAL_MP4.get(stem)
    if not mp4:
        stats["제외:채점 전용 영상 아님"] += 1
    return mp4


def fire_start(mp4):
    """KISA XML(영상 옆 같은 이름 .xml)의 Alarm/StartTime 중 가장 이른 것(초). 없으면 None."""
    import xml.etree.ElementTree as ET
    x = mp4.with_suffix(".xml")
    if not x.exists():
        return None
    def secs(txt):
        p = [int(v) for v in str(txt).strip().split(":")]
        while len(p) < 3:
            p.insert(0, 0)
        return p[0] * 3600 + p[1] * 60 + p[2]
    st = [secs(al.findtext("StartTime")) for al in ET.parse(x).getroot().iter("Alarm") if al.findtext("StartTime")]
    return min(st) if st else None


def sam_cls(obj):                                   # SAM 저장소 객체 번호 → 클래스(대시보드 규약: 화재 1=불(0) 2=연기(1), 사람 0)
    return max(0, min(1, int(obj) - 1)) if a.mode == "fire" else 0


frames = {}                                         # (stem, t) → [(cls, [x,y,w,h])]   (빈 목록 = 배경)
src = {}
# 1) 손라벨 eval 행
rows = json.load(io.open(V / f"data/학습데이터/손라벨/{a.mode}_labels.json", encoding="utf-8"))
for r in rows:
    if r["clip"] not in EVAL_MP4:                    # 채점 클립인가로 판단(eval 표시는 보조. 표시가 빠진 행도 놓치지 않게)
        continue
    key = (r["clip"], round(float(r["t"]) * 2) / 2)
    frames.setdefault(key, []); src[key] = "hand"
    if int(r.get("cls", -1)) >= 0:
        frames[key].append((int(r["cls"]), [r["x"], r["y"], r["w"], r["h"]]))
# 2) SAM 전파 결과(채점 전용 클립만, 손라벨 없는 프레임만)
for f in sorted((V / "data/학습데이터/자동라벨/sam2").glob("*.json")):
    stem = f.stem
    if stem not in EVAL_MP4:
        continue
    d = json.load(io.open(f, encoding="utf-8"))
    for k, objs in (d.get("frames") or {}).items():
        key = (stem, round(float(k) * 2) / 2)
        if key in frames or not objs:
            continue
        frames[key] = [(sam_cls(o), list(b)) for o, b in objs.items()]; src[key] = "sam"
# 3) 배경 프레임: 정답 화재 발생 시각 앞 구간에서 균등 표본
if a.bg > 0:
    for stem in sorted({s for s, _ in frames}):
        mp4 = eval_clip(stem)
        if not mp4:
            continue
        st = fire_start(mp4)
        if st is None:
            stats["배경 생략:발생시각 없음"] += 1; continue
        end = st - a.bg_margin
        if end < 2:
            stats["배경 생략:구간 짧음"] += 1; continue
        for i in range(a.bg):
            t = round((end * (i + 0.5) / a.bg) * 2) / 2
            key = (stem, t)
            if key not in frames:
                frames[key] = []; src[key] = "bg"

# 프레임 뽑기 + 라벨 쓰기
(OUT / "images").mkdir(parents=True, exist_ok=True); (OUT / "labels").mkdir(parents=True, exist_ok=True)
lst = []; caps = {}
for (stem, t), boxes in sorted(frames.items()):
    mp4 = eval_clip(stem)
    if not mp4:
        continue
    jp = OUT / "images" / f"{stem}_{t:g}.jpg"
    if not jp.exists():
        cap = caps.get(mp4) or caps.setdefault(mp4, cv2.VideoCapture(str(mp4)))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(t * fps)), 0)); ok, fr = cap.read()
        if not ok:
            stats["프레임 읽기 실패"] += 1; continue
        cv2.imwrite(str(jp), fr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    (OUT / "labels" / f"{jp.stem}.txt").write_text("".join("%d %.6f %.6f %.6f %.6f\n" % (c, b[0] + b[2] / 2, b[1] + b[3] / 2, b[2], b[3]) for c, b in boxes))
    lst.append(str(jp)); stats[f"프레임:{src[(stem, t)]}"] += 1
for c in caps.values():
    c.release()
(OUT / "val.txt").write_text("\n".join(lst) + "\n")
(OUT / "data.yaml").write_text(f"path: {OUT}\ntrain: {OUT}/val.txt\nval: {OUT}/val.txt\nnc: {len(NAMES)}\nnames: {NAMES}\n")   # 검증 전용. train 칸은 ultralytics 형식 때문에 채울 뿐 학습에 쓰지 않는다
clips = sorted({s for s, _ in frames})
meta = {"name": NAME, "mode": a.mode, "built": time.strftime("%F %T"), "frames": len(lst), "clips": clips,
        "boxes": sum(len(b) for b in frames.values()), "bg_per_clip": a.bg, "bg_margin_s": a.bg_margin,
        "source": "손라벨 eval 행 > SAM 전파(채점 전용 클립) > 발생 전 배경 표본", "use": "검증 전용. 학습 금지", "stats": dict(stats)}
(OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료 → {OUT}  프레임 {len(lst)} · 클립 {len(clips)} · 박스 {meta['boxes']}  {dict(stats)}")

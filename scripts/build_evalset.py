# -*- coding: utf-8 -*-
"""검증셋 빌더: 채점 전용 카테고리(use: eval)의 영상에서 사람이 만든 라벨만 모아 mAP 검증셋을 만든다. 학습에 절대 넣지 않는다(검증 전용).
  포함  1) 손라벨 eval 행(cls -1 = 검토완료 → 박스 없는 배경 프레임)
        2) SAM 전파 결과(자동라벨/sam2/<stem>.json) — 채점 전용 카테고리 클립만. 손라벨 프레임이 있으면 손라벨이 우선
        3) 라벨 범위 밖 = 대상 없음(--neg-step 초 간격, 2026-10-02): 편마다 박스 있는 첫 ~ 끝 시각 밖을 빈 프레임으로 넣는다.
           범위 앞뒤 --neg-margin 초는 뺀다. 쓰러짐 편은 안 넣는다(넘어지기 전 · 뒤에도 사람이 있다). 범위 안 라벨 없는 칸도 안 넣는다(방화는 1초 간격으로 친다)
           사용자가 대상이 나오는 동안을 다 쳐 두었다는 전제다(10-02 범위 밖 9장 확인: 불 꺼짐 · 구역에 사람 없음)
  출력  data/학습데이터/evalset_<mode>/{images,labels}/ + val.txt + meta.json
  사용  python scripts/build_evalset.py fire [--name evalset_fire] [--neg-step 2] [--neg-margin 3]
러너(exp_queue.py)는 defaults.val_set 에 이 val.txt 경로를 주면 val_small 대신 이걸 검증셋으로 쓴다."""
import sys, io, json, argparse, collections, time
from pathlib import Path
import cv2
import kisa_paths as KP            # 저장소 루트는 여기 한 곳에서만 정의한다
V = KP.V
sys.path.insert(0, str(V / "dash_v2")); import gt_adapters as GTA
ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["fire", "person", "intrusion", "loitering", "falldown"]); ap.add_argument("--name", default=None)
ap.add_argument("--neg-step", type=float, default=2.0, help="라벨 범위 밖에서 빈 프레임을 뽑는 간격(초). 0 = 안 뽑음")
ap.add_argument("--neg-margin", type=float, default=3.0, help="라벨 범위 앞뒤 여유(초). 이 안쪽은 빈 프레임으로 안 쓴다(들어오는 사람 · 불씨가 걸칠 수 있다)")
a = ap.parse_args()
RAW = V / "data/원본데이터"; D = GTA.Datasets(V / "configs/datasets.yaml", RAW)
NAME = a.name or f"evalset_{a.mode}"; OUT = V / "data/학습데이터" / NAME
NAMES = ["fire", "smoke"] if a.mode == "fire" else ["person"]
LABELS = "fire" if a.mode == "fire" else "person"          # 손라벨 파일(fire_labels.json · person_labels.json)
# 항목별 평가셋(2026-10-02): intrusion · loitering · falldown 은 그 항목 폴더 영상만, person = 침입 + 배회 + 쓰러짐(예전과 같음)
WANT = {"fire": {"fire"}, "intrusion": {"intrusion"}, "loitering": {"loitering"}, "falldown": {"falldown"},
        "person": {"intrusion", "loitering", "falldown"}}[a.mode]
stats = collections.Counter()


EVAL_CATS = sorted(c for c, cfg in D.all().items() if cfg.get("use") == "eval")
def _clip_item(p):                                  # 채점 카테고리는 항목별 하위 폴더(방화/침입/배회/쓰러짐)가 섞여 있다 → 폴더 이름으로 항목
    s = str(p)
    for k, v in (("방화", "fire"), ("침입", "intrusion"), ("배회", "loitering"), ("쓰러짐", "falldown")):
        if k in s:
            return v
    return None
EVAL_MP4 = {p.stem: p for c in EVAL_CATS for p in (RAW / c).rglob("*.mp4") if _clip_item(p) in WANT}   # 채점 전용 카테고리 안만 한 번 훑는다


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


FALL_WIN = (-2.0, 10.0)                             # 쓰러짐 편은 정답 시각 기준 이 창 안 프레임만(KISA 채점 창, 2026-10-02 사용자)


def fall_keep(stem, t):
    """쓰러짐 편이면 정답 -2 ~ +10초 안일 때만 True. 다른 항목은 늘 True.
    창 밖 손라벨('사람 없음' 행 포함) · SAM 전파는 버린다(넘어지기 전 · 일어난 뒤 장면은 쓰러짐 평가가 아니다)."""
    mp4 = EVAL_MP4.get(stem)
    if not mp4 or _clip_item(mp4) != "falldown":
        return True
    st = fire_start(mp4)
    if st is not None and st + FALL_WIN[0] <= t <= st + FALL_WIN[1]:
        return True
    stats["제외:쓰러짐 창 밖"] += 1
    return False


def sam_cls(obj):                                   # SAM 저장소 객체 번호 → 클래스(대시보드 규약: 화재 1=불(0) 2=연기(1), 사람 0)
    return max(0, min(1, int(obj) - 1)) if a.mode == "fire" else 0


frames = {}                                         # (stem, t) → [(cls, [x,y,w,h])]   (빈 목록 = 배경)
src = {}
# 1) 손라벨 eval 행
rows = json.load(io.open(V / f"data/학습데이터/손라벨/{LABELS}_labels.json", encoding="utf-8"))
for r in rows:
    if r["clip"] not in EVAL_MP4:                    # 채점 클립인가로 판단(eval 표시는 보조. 표시가 빠진 행도 놓치지 않게)
        continue
    key = (r["clip"], round(float(r["t"]) * 2) / 2)
    if not fall_keep(*key):
        continue
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
        if key in frames or not objs or not fall_keep(*key):
            continue
        frames[key] = [(sam_cls(o), list(b)) for o, b in objs.items()]; src[key] = "sam"
# 3) 라벨 범위 밖 = 대상 없음. 편마다 박스 있는 첫 ~ 끝 시각(± 여유) 밖을 neg_step 초 간격으로
if a.neg_step > 0:
    for stem in sorted({s for s, _ in frames}):
        mp4 = eval_clip(stem)
        if not mp4:
            continue
        if _clip_item(mp4) == "falldown":           # 넘어지기 전 · 뒤에도 그 사람이 있다(081 은 5명). '대상 없음' 으로 못 쓴다
            stats["범위 밖 생략:쓰러짐 편"] += 1; continue
        pos = [t for (c, t), b in frames.items() if c == stem and b]
        if not pos:
            continue
        lo, hi = min(pos) - a.neg_margin, max(pos) + a.neg_margin
        cap = cv2.VideoCapture(str(mp4)); dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30.0); cap.release()
        for k in range(int((dur - 1) / a.neg_step) + 1):
            t = round(k * a.neg_step * 2) / 2
            if (t < lo or t > hi) and (stem, t) not in frames:
                frames[(stem, t)] = []; src[(stem, t)] = "out"

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
meta = {"name": NAME, "mode": a.mode, "items": sorted(WANT), "built": time.strftime("%F %T"), "frames": len(lst), "clips": clips,
        "boxes": sum(len(b) for b in frames.values()), "neg_step_s": a.neg_step, "neg_margin_s": a.neg_margin,
        "source": "손라벨 eval 행 > SAM 전파(채점 전용 클립) > 라벨 범위 밖 빈 프레임(쓰러짐 제외)", "use": "검증 전용. 학습 금지", "stats": dict(stats)}
(OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료 → {OUT}  프레임 {len(lst)} · 클립 {len(clips)} · 박스 {meta['boxes']}  {dict(stats)}")

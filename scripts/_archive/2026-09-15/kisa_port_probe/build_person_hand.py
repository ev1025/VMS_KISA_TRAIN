# -*- coding: utf-8 -*-
"""사람 손라벨 학습셋: 손라벨(person_labels.json) ∪ SAM 전파(자동라벨/sam2, 손라벨 없는 프레임만) → YOLO 세트.
프레임은 원본 mp4 에서 그 시각을 뽑아 jpg 로 저장(원본은 읽기만). 라벨 cls 는 전부 0(person).
출력: data/학습데이터/person_hand_<날짜>/{images,labels}/{train,val}, train.txt(person_v3 학습셋 + 손라벨 ×OVER), val.txt, data.yaml
사용: python build_person_hand.py [출력이름]"""
import sys, os, io, json, glob, collections, shutil
import cv2
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
NAME = sys.argv[1] if len(sys.argv) > 1 else "person_hand_20260910"
OUT = f"{V}/data/학습데이터/{NAME}"
BASE = f"{V}/data/학습데이터/person_v3"          # 배포 사람 탐지기 person_v3 의 학습셋(33k) 을 밑에 깐다(잊지 않게)
OVER = 5                                          # 손라벨 프레임 반복 배수(화재 큐의 human_fire ×5 와 같은 규칙)
VAL_CLIPS = {"C045200_003", "C056303_005", "E02_002"}   # 클립 단위로 검증 분리(같은 클립 프레임이 학습·검증에 섞이지 않게)

rows = json.load(io.open(f"{V}/data/학습데이터/손라벨/person_labels.json", encoding="utf-8"))
src_of = {}                                       # stem → 원본 mp4 상대경로
frames = collections.defaultdict(dict)            # stem → {t: [[x,y,w,h],...]}
for r in rows:
    if r.get("cls", -1) < 0:
        continue
    st = r["clip"]; t = round(float(r["t"]) * 2) / 2
    frames[st].setdefault(t, []).append([r["x"], r["y"], r["w"], r["h"]])
    if r.get("src"):
        src_of[st] = r["src"]
n_hand = sum(len(v) for v in frames.values())
for f in glob.glob(f"{V}/data/학습데이터/자동라벨/sam2/*.json"):
    d = json.load(io.open(f, encoding="utf-8")); st = d.get("clip") or os.path.basename(f)[:-5]
    for k, objs in (d.get("frames") or {}).items():
        t = round(float(k) * 2) / 2
        if not objs or t in frames[st]:
            continue                              # 손라벨 프레임은 손라벨만
        frames[st][t] = [list(b) for b in objs.values()]
n_all = sum(len(v) for v in frames.values())
print(f"손라벨 {n_hand}프레임 + SAM {n_all - n_hand}프레임 = {n_all}프레임 · 클립 {len(frames)}")


def find_mp4(st):
    if st in src_of:
        p = f"{V}/data/원본데이터/{src_of[st]}"
        if os.path.exists(p):
            return p
    hits = glob.glob(f"{V}/data/원본데이터/**/{st}.mp4", recursive=True)
    return hits[0] if hits else None


for sp in ("train", "val"):
    os.makedirs(f"{OUT}/images/{sp}", exist_ok=True); os.makedirs(f"{OUT}/labels/{sp}", exist_ok=True)
made = {"train": [], "val": []}
for st, ts in sorted(frames.items()):
    mp4 = find_mp4(st)
    if not mp4:
        print("영상 없음", st); continue
    if "방화" in mp4 or "산불" in mp4:
        print("화재 클립 제외", st); continue          # SAM 저장소의 불·연기 박스는 사람 세트에 안 넣는다
    sp = "val" if st in VAL_CLIPS else "train"
    cap = cv2.VideoCapture(mp4); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    for t in sorted(ts):
        name = f"{st}_{int(round(t * 10)):05d}"
        jp = f"{OUT}/images/{sp}/{name}.jpg"; lp = f"{OUT}/labels/{sp}/{name}.txt"
        if not os.path.exists(jp):
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(t * fps)), 0))
            ok, fr = cap.read()
            if not ok:
                print("프레임 실패", st, t); continue
            cv2.imwrite(jp, fr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        io.open(lp, "w").write("".join(f"0 {b[0] + b[2] / 2:.6f} {b[1] + b[3] / 2:.6f} {b[2]:.6f} {b[3]:.6f}\n" for b in ts[t]))
        made[sp].append(jp)
    cap.release()
print(f"저장: train {len(made['train'])} · val {len(made['val'])}")

base_train, base_val = [], []                     # 의사라벨 세트(person_v3 등)는 섞지 않는다: 사용자가 손라벨·전파한 프레임만
io.open(f"{OUT}/train.txt", "w").write("\n".join(base_train + made["train"] * OVER) + "\n")
io.open(f"{OUT}/val.txt", "w").write("\n".join(base_val + made["val"]) + "\n")
io.open(f"{OUT}/data.yaml", "w").write(f"path: {OUT}\ntrain: {OUT}/train.txt\nval: {OUT}/val.txt\nnc: 1\nnames: ['person']\n")
meta = {"name": NAME, "hand_frames": n_hand, "sam_frames": n_all - n_hand, "clips": sorted(frames), "val_clips": sorted(VAL_CLIPS), "oversample": OVER,
        "base": "none(손라벨·SAM 만)", "base_train": len(base_train), "train_list": len(base_train) + len(made["train"]) * OVER, "val_list": len(base_val) + len(made["val"])}
io.open(f"{OUT}/meta.json", "w", encoding="utf-8").write(json.dumps(meta, ensure_ascii=False, indent=1))
print(json.dumps(meta, ensure_ascii=False))

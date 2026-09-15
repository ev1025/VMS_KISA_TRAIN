# -*- coding: utf-8 -*-
"""학습 이미지를 긴 변 960 으로 미리 줄인 사본을 만든다 → /NHNHOME/vms_r960
이유: 학습 병목이 저장소가 아니라 JPEG 디코딩이었다(실측 원본 1920 = 261장/초, 960 사본 = 727장/초, 8워커).
960 인 이유: 지금 레시피의 multi_scale 상한이 imgsz 640 × 1.5 = 960 이라, 학습이 쓰는 어떤 크기에서도 화질 손실이 없다.
라벨은 정규화 좌표라 그대로 쓴다(하드링크). 이미 960 이하인 이미지도 하드링크(재인코딩 안 함).
원본·미러는 읽기만. 다시 실행하면 끝난 데이터셋은 건너뛴다.
사용: python make_r960.py [데이터셋 ...]"""
import os, sys, glob, json, time, shutil
from concurrent.futures import ThreadPoolExecutor
import cv2
cv2.setNumThreads(1)                                   # 스레드풀로 병렬화하므로 OpenCV 내부 스레드는 끈다(학습 CPU 침범 방지)

V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
MIRROR = "/NHNHOME/vms_mirror"
# 긴 변은 인자로 받는다. 학습 상한(imgsz x (1+multi_scale))보다 작은 사본을 쓰면
# 확대 보간이 되어 '고해상도 학습' 이 이름만 남는다. 상한 1280 실험에는 --side 1280 이 필요하다.
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
SIDE = 960
if "--side" in sys.argv:
    SIDE = int(sys.argv[sys.argv.index("--side") + 1])
    _args = [a for a in _args if a != str(SIDE)]
DST = f"/NHNHOME/vms_r{SIDE}"
QUAL, THREADS = 92, 24
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT = ["aihub71751_48k", "fasdd_yolo", "fasdd_snowfog", "human_fire",       # wildpos·wildall 이 쓰는 것 먼저
           "wildfire_pos_yolo", "wildfire_fog_neg",
           "azimjaan_yolo", "dfire_yolo", "aihub71751_24k"]


def src_of(name):
    for root in ("학습데이터", "원본데이터"):
        for base in (MIRROR + "/data", V + "/data"):    # NVMe 미러가 있으면 거기서 읽는다(로컬이라 빠르다)
            p = f"{base}/{root}/{name}"
            if os.path.isdir(p):
                return p, root
    return None, None


def one(args):
    src, dst = args
    if os.path.exists(dst):
        return 0
    im = cv2.imread(src)
    if im is None:
        return 0
    h, w = im.shape[:2]
    if max(h, w) <= SIDE:                               # 이미 작으면 재인코딩하지 않는다(화질 보존 + 빠름)
        try:
            os.link(src, dst); return 1
        except OSError:
            shutil.copyfile(src, dst); return 1
    r = SIDE / max(h, w)
    im = cv2.resize(im, (round(w * r), round(h * r)), interpolation=cv2.INTER_AREA)
    ext = os.path.splitext(dst)[1] or ".jpg"
    ok, buf = cv2.imencode(ext, im, [int(cv2.IMWRITE_JPEG_QUALITY), QUAL] if ext.lower() in (".jpg", ".jpeg") else [])
    if not ok:
        return 0
    tmp = dst + ".tmp"                                  # 임시 이름은 확장자가 없어도 된다(바이트로 직접 쓴다)
    open(tmp, "wb").write(buf.tobytes()); os.replace(tmp, dst)
    return 1


for name in (_args or DEFAULT):
    src, root = src_of(name)
    if not src:
        print("없음:", name, flush=True); continue
    out = f"{DST}/data/{root}/{name}"
    mark = f"{out}/.r{SIDE}_ok"
    imgs = [p for p in glob.glob(f"{src}/images/**/*", recursive=True) if os.path.splitext(p)[1].lower() in IMG_EXT]
    if os.path.exists(mark) and json.load(open(mark)).get("images") == len(imgs):
        print(f"건너뜀 {name}: 이미 완료({len(imgs)}장)", flush=True); continue
    t0 = time.time()
    jobs = []
    for p in imgs:
        d = out + p[len(src):]
        os.makedirs(os.path.dirname(d), exist_ok=True)
        jobs.append((p, d))
    with ThreadPoolExecutor(THREADS) as ex:
        n = sum(ex.map(one, jobs))
    for lp in glob.glob(f"{src}/labels/**/*", recursive=True):   # 라벨은 정규화 좌표 → 그대로(하드링크)
        d = out + lp[len(src):]
        if os.path.isdir(lp):
            os.makedirs(d, exist_ok=True); continue
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if not os.path.exists(d):
            try:
                os.link(lp, d)
            except OSError:
                shutil.copyfile(lp, d)
    for extra in glob.glob(f"{src}/*.yaml"):
        shutil.copyfile(extra, out + extra[len(src):])
    sz = sum(os.path.getsize(p) for p, _ in jobs[:200]) / max(1, min(200, len(jobs)))
    json.dump({"images": len(imgs), "written": n, "src": src, "at": time.strftime("%F %T"), "sec": round(time.time() - t0)}, open(mark, "w"))
    print(f"완료 {name}: {len(imgs):,}장 {(time.time() - t0) / 60:.1f}분 · 용량 {sum(os.path.getsize(d) for _, d in jobs if os.path.exists(d)) / 2 ** 30:.1f}GB", flush=True)
print(f"{SIDE} 사본 종료")

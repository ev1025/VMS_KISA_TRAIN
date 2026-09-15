# -*- coding: utf-8 -*-
"""읽기 속도만 비교(GPU 안 씀): Lustre 원본 vs NVMe 미러에서 같은 이미지 N장을 무작위 순서로 열고 디코딩한다.
학습 데이터로더가 하는 일(파일 열기 + JPEG 디코딩)과 같은 모양이라, 미러가 실제로 얼마나 빠른지 바로 나온다.
사용: python bench_io.py [데이터셋] [장수] [워커수]"""
import sys, os, time, random, glob
from concurrent.futures import ThreadPoolExecutor
import cv2
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
DS = sys.argv[1] if len(sys.argv) > 1 else "aihub71751_48k"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
W = int(sys.argv[3]) if len(sys.argv) > 3 else 8

def files(root):
    for sub in ("images/train", "images"):
        g = sorted(glob.glob(f"{root}/{sub}/*.jpg") + glob.glob(f"{root}/{sub}/*.png"))
        if g:
            return g
    return []

srcs = {"Lustre": f"{V}/data/원본데이터/{DS}", "NVMe": f"/NHNHOME/vms_mirror/data/원본데이터/{DS}"}
if not os.path.isdir(srcs["Lustre"]):
    srcs = {"Lustre": f"{V}/data/학습데이터/{DS}", "NVMe": f"/NHNHOME/vms_mirror/data/학습데이터/{DS}"}
base = files(srcs["Lustre"])
assert base, f"이미지 없음: {srcs['Lustre']}"
rnd = random.Random(0)
pick = rnd.sample(range(len(base)), min(N, len(base)))     # 두 곳에서 같은 파일을 같은 순서로 읽는다

print(f"{DS} · {len(pick)}장 · 워커 {W}")
for label, root in srcs.items():
    fs = files(root)
    if not fs:
        print(f"{label}: 없음"); continue
    paths = [fs[i] for i in pick]
    def rd(p):
        im = cv2.imread(p)
        return 0 if im is None else im.nbytes
    t0 = time.time()
    with ThreadPoolExecutor(W) as ex:
        tot = sum(ex.map(rd, paths))
    dt = time.time() - t0
    print(f"{label:7s} {dt:6.1f}초 · 초당 {len(paths)/dt:6.1f}장 · 디코딩 후 {tot/2**30:.1f}GB")

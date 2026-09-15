# -*- coding: utf-8 -*-
"""학습 데이터셋을 Lustre → 로컬 NVMe(/NHNHOME/vms_mirror) 로 미러링.
Lustre 는 소파일 메타데이터가 느려 RAM 캐시 없이 읽으면 에폭 시간이 두 배가 된다(실측 10분 → 19분).
NVMe 사본을 쓰면 RAM 캐시 없이도 원래 속도가 나온다 = OOM 원인(대용량 RAM 캐시) 자체를 없앤다.

- 심링크는 실체로 푼다(tar -h). 원본은 읽기만.
- 데이터셋마다 .mirror_ok 표식(파일 수·용량) → 다시 실행하면 이미 끝난 것은 건너뛴다.
- ionice/nice 로 낮은 우선순위(돌고 있는 학습의 I/O 를 덜 방해한다).
사용: python mirror_to_nvme.py [데이터셋 이름 ...]   (인자 없으면 큐가 쓰는 전부)"""
import os, sys, subprocess, shutil, time, json
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
DST = "/NHNHOME/vms_mirror"
ROOTS = [f"{V}/data/학습데이터", f"{V}/data/원본데이터"]
DEFAULT = ["aihub71751_48k", "fasdd_yolo", "fasdd_snowfog", "human_fire",          # 거의 모든 실험이 쓰는 것부터
           "aihub71751_24k", "azimjaan_yolo", "dfire_yolo", "wildfire_fog_neg", "wildfire_pos_yolo"]


def src_of(name):
    for r in ROOTS:
        if os.path.isdir(f"{r}/{name}"):
            return f"{r}/{name}", os.path.basename(r)
    return None, None


def count_files(p):
    n = 0
    for _, _, fs in os.walk(p):
        n += len(fs)
    return n


def free_gb(p):
    s = os.statvfs(p)
    return s.f_bavail * s.f_frsize / 2 ** 30


names = sys.argv[1:] or DEFAULT
for name in names:
    src, root = src_of(name)
    if not src:
        print("없음:", name, flush=True); continue
    dst = f"{DST}/data/{root}/{name}"
    mark = f"{dst}/.mirror_ok"
    n_src = count_files(src)
    if os.path.exists(mark):
        try:
            ok = json.load(open(mark))
        except Exception:
            ok = {}
        if ok.get("files") == n_src:
            print(f"건너뜀 {name}: 이미 미러됨({n_src}개)", flush=True); continue
    need = subprocess.run(["du", "-shLB1", src], capture_output=True, text=True).stdout.split()[0]
    need_gb = int(need) / 2 ** 30
    if free_gb(DST if os.path.isdir(DST) else "/NHNHOME") < need_gb + 20:
        print(f"공간 부족: {name} {need_gb:.0f}GB 필요, 남은 {free_gb('/NHNHOME'):.0f}GB", flush=True); break
    os.makedirs(dst, exist_ok=True)
    t0 = time.time()
    print(f"미러 {name} {need_gb:.1f}GB {n_src}개 …", flush=True)
    # tar 파이프: 소파일도 스트림 하나로 흐른다(cp -r 보다 Lustre 메타데이터 왕복이 적다). -h = 심링크를 실체로
    rc = subprocess.run(f"nice -n 10 ionice -c2 -n7 tar -C {src!r} -chf - . | tar -C {dst!r} -xf -",
                        shell=True).returncode
    if rc != 0:
        print(f"실패 {name} rc={rc}", flush=True); continue
    json.dump({"files": n_src, "src": src, "at": time.strftime("%F %T"), "sec": round(time.time() - t0)}, open(mark, "w"))
    print(f"완료 {name} {(time.time() - t0) / 60:.1f}분 · 남은 공간 {free_gb('/NHNHOME'):.0f}GB", flush=True)
print("미러 종료")

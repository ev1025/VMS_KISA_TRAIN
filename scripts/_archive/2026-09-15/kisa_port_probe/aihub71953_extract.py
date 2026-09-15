# -*- coding: utf-8 -*-
"""AI허브 71953(다각도 CCTV 생활안전) 부분 데이터 정리.
받은 zip(_dl/ 아래 .part 조각 → 합침) 을 data/원본데이터/aihub71953_다각도/<시나리오>/<이벤트>/ 로 풀고,
라벨 zip(_labels/) 의 <이벤트>.json 을 같은 이벤트 폴더에 둔다(영상 옆 정답 = 대시보드가 읽어 정답라벨 복사본을 만든다).
원본 zip 은 지우지 않는다(_dl/ 에 그대로). 다시 실행해도 있는 파일은 건너뛴다.
사용: python aihub71953_extract.py [--dry]"""
import sys, os, io, glob, json, zipfile, shutil, re
ROOT = "/NHNHOME/WORKSPACE/26mss002_E3/vms/data/원본데이터/aihub71953_다각도"
DRY = "--dry" in sys.argv
SCEN = {"스토킹_특정구역내지속배회": "배회_구역", "스토킹_특정인물을뒤따라가며배회": "배회_뒤따름", "침입_경계선을통한침입": "침입_경계선", "침입_비정상적인경로로의침범": "침입_비정상경로"}


def merged_zips(base):
    """<이름>.zip.part0.. 조각을 <이름>.zip 으로 합친다(이미 있으면 그대로). 합친 zip 경로 목록."""
    out = []
    for p0 in sorted(glob.glob(f"{base}/**/*.zip.part0", recursive=True)):
        z = p0[:-len(".part0")]
        if not os.path.exists(z):
            parts = sorted(glob.glob(z + ".part*"), key=lambda s: int(re.search(r"part(\d+)$", s).group(1)))
            print("합침", os.path.basename(z), len(parts), "조각", flush=True)
            if not DRY:
                with open(z + ".tmp", "wb") as w:
                    for q in parts:
                        with open(q, "rb") as r:
                            shutil.copyfileobj(r, w, 1 << 24)
                os.replace(z + ".tmp", z)
                for q in parts:
                    os.remove(q)
        out.append(z)
    out += [z for z in glob.glob(f"{base}/**/*.zip", recursive=True) if z not in out and not glob.glob(z + ".part*")]
    return sorted(set(out))


def scen_of(name):
    for k, v in SCEN.items():
        if k in name:
            return v
    return None


n_mp4 = n_json = 0
for z in merged_zips(f"{ROOT}/_dl"):                      # 영상
    sc = scen_of(os.path.basename(z))
    if not sc:
        continue
    try:
        zf = zipfile.ZipFile(z)
    except Exception as e:
        print("zip 깨짐", z, e); continue
    for n in zf.namelist():
        if not n.lower().endswith(".mp4"):
            continue
        fn = os.path.basename(n); ev = fn.rsplit("_c", 1)[0]          # bl_e0001_c1.mp4 → 이벤트 bl_e0001
        dst = f"{ROOT}/{sc}/{ev}/{fn}"
        if os.path.exists(dst):
            continue
        n_mp4 += 1
        if DRY:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with zf.open(n) as r, open(dst + ".tmp", "wb") as w:
            shutil.copyfileobj(r, w, 1 << 24)
        os.replace(dst + ".tmp", dst)
    print(f"{os.path.basename(z)} → {sc}: mp4 {n_mp4}장 누적", flush=True)
for z in merged_zips(f"{ROOT}/_labels"):                  # 라벨(이벤트 JSON) → 같은 이벤트 폴더
    sc = scen_of(os.path.basename(z))
    if not sc:
        continue
    zf = zipfile.ZipFile(z)
    for n in zf.namelist():
        if not n.lower().endswith(".json"):
            continue
        ev = os.path.splitext(os.path.basename(n))[0]
        dst = f"{ROOT}/{sc}/{ev}/{os.path.basename(n)}"
        if os.path.exists(dst) or not os.path.isdir(os.path.dirname(dst)):
            continue                                       # 영상이 없는 이벤트의 라벨은 두지 않는다
        n_json += 1
        if not DRY:
            open(dst, "wb").write(zf.read(n))
print(f"완료: mp4 {n_mp4} · json {n_json}  ({'dry' if DRY else 'written'})")

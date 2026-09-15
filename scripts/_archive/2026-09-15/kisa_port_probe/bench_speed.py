# -*- coding: utf-8 -*-
"""학습 속도 설정 비교(짧은 실측). 같은 데이터·같은 모델로 설정만 바꿔 2에폭씩 돌리고 초당 장수를 잰다.
목적: multi_scale·batch·workers·cache 를 바꾸면 실제로 얼마나 빨라지는지 숫자로 확인한 뒤에 큐 레시피를 정한다.
(진행 중인 애블레이션 큐의 레시피는 건드리지 않는다. 비교가 깨지기 때문)

사용: python bench_speed.py [데이터셋이름] [에폭]
출력: _kisa_port/bench_speed_<시각>.md
"""
import sys, os, time, json, io, glob, subprocess
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
os.chdir(V)
DS = sys.argv[1] if len(sys.argv) > 1 else "aihub71751_24k"
EPOCHS = int(sys.argv[2]) if len(sys.argv) > 2 else 2

MIRROR = f"/NHNHOME/vms_mirror/data/학습데이터/{DS}"
SRC = MIRROR if os.path.exists(f"{MIRROR}/.mirror_ok") else f"{V}/data/학습데이터/{DS}"
imgs = sorted(glob.glob(f"{SRC}/images/train/*") or glob.glob(f"{SRC}/images/*"))
assert imgs, f"이미지 없음: {SRC}"
d = f"{V}/_exp/_bench_{DS}"
os.makedirs(d, exist_ok=True)
io.open(f"{d}/train.txt", "w").write("\n".join(imgs) + "\n")
io.open(f"{d}/val.txt", "w").write("\n".join(imgs[:600]) + "\n")
io.open(f"{d}/data.yaml", "w").write(f"path: {d}\ntrain: {d}/train.txt\nval: {d}/val.txt\nnc: 2\nnames: ['fire','smoke']\n")

CASES = [                                              # (이름, 배치, 워커, multi_scale, cache)
    ("기준(현재 큐 설정)", 128, 8, 0.5, "False"),
    ("워커16", 128, 16, 0.5, "False"),
    ("워커16+멀티스케일끔", 128, 16, 0.0, "False"),
    ("워커16+배치256", 256, 16, 0.5, "False"),
    ("워커16+디스크캐시", 128, 16, 0.5, "disk"),
]
rows = []
for name, batch, workers, ms, cache in CASES:
    run = f"{V}/runs/_bench/{name.replace('+', '_').replace('(', '').replace(')', '')}"
    subprocess.run(["rm", "-rf", run])
    cmd = [f"{V}/.venv/bin/python", "model.py", "train", "--models", "yolo11s", "--data", f"{d}/data.yaml",
           "--project", run, "--device", "0", "--batch", str(batch), "--epochs", str(EPOCHS),
           "--imgsz", "640", "--no-export", "--force", "--cache", cache, "--workers", str(workers),
           "--extra", f"multi_scale={ms}", "val=True", "plots=False"]
    t0 = time.time()
    log = f"{V}/logs/queue/bench_{name}.log".replace(" ", "_")
    with open(log, "w") as lf:
        rc = subprocess.run(cmd, cwd=V, stdout=lf, stderr=subprocess.STDOUT).returncode
    dt = time.time() - t0
    csvs = glob.glob(f"{run}/*/results.csv")
    per = None
    if csvs:
        import csv as _csv
        rr = list(_csv.DictReader(io.open(csvs[0], encoding="utf-8")))
        if len(rr) >= 2:
            per = (float(rr[-1]["time"]) - float(rr[-2]["time"])) / 60      # 마지막 에폭(초기화 제외)
    rows.append({"설정": name, "배치": batch, "워커": workers, "multi_scale": ms, "cache": cache,
                 "분/에폭": round(per, 2) if per else None,
                 "초당장수": round(len(imgs) / (per * 60), 1) if per else None,
                 "총초": round(dt), "rc": rc})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)

stamp = time.strftime("%Y%m%d_%H%M")
md = [f"# 학습 속도 설정 비교 {stamp}", "", f"데이터셋 {DS} · {len(imgs):,}장 · 경로 {'NVMe 미러' if SRC == MIRROR else 'Lustre'} · yolo11s · {EPOCHS}에폭", "",
      "| 설정 | 배치 | 워커 | multi_scale | cache | 분/에폭 | 초당 장수 |", "|---|---|---|---|---|---|---|"]
for r in rows:
    md.append(f"| {r['설정']} | {r['배치']} | {r['워커']} | {r['multi_scale']} | {r['cache']} | {r['분/에폭']} | {r['초당장수']} |")
io.open(f"{V}/_kisa_port/bench_speed_{stamp}.md", "w", encoding="utf-8").write("\n".join(md) + "\n")
print("\n".join(md))

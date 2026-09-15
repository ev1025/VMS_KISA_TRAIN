"""라이브 BotSortPersons 트랙을 jsonl 로 덤프(원본 dumps/loiter_trk_id 와 같은 형식) → 원본과 ID 차이 비교용."""
import json, sys, os
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools"); import kisa_items as K
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"; D = f"{V}/data/원본데이터/kisa_배포_검증영상/deploy_val/배회(30개)/배포"
stem = sys.argv[1]; out = f"{V}/dumps/loiter_live_bs/{stem}.jsonl"; os.makedirs(os.path.dirname(out), exist_ok=True)
bs = K.BotSortPersons(f"{V}/_kisa_port/weights/kisa/person_v2.pt")
src = K.FileSource([f"{D}/{stem}.mp4"], stride_s=0.5)
with open(out, "w") as w:
    while True:
        f = src.read()
        if f is None: break
        w.write(json.dumps({"t": round(f.ts, 2), "boxes": [list(b) for b in bs.update(f.bgr)]}) + "\n")
print("saved", out)

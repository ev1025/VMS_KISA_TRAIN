"""SAM2 비디오 전파 실측: DINO 박스를 씨앗으로 넣고 전파했을 때
출력 형태·속도·박스 품질을 본다. 여기서 되는 걸 확인한 뒤 배치로 만든다."""
import os, sys, time, torch, cv2, numpy as np
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools")
from transformers import (AutoProcessor, AutoModelForZeroShotObjectDetection,
                          Sam2VideoProcessor, Sam2VideoModel)

V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
MP4 = f"{V}/data/원본데이터/kisa_연구개발_사람영상/1. 배회(325개)/C045100_003.mp4"
PROMPT = "a person. a pedestrian. a human. a man walking. a person with an umbrella."
dev = "cuda"

gproc = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-base")
gd = AutoModelForZeroShotObjectDetection.from_pretrained("IDEA-Research/grounding-dino-base").to(dev).eval()
SID = "facebook/sam2.1-hiera-small"
sproc = Sam2VideoProcessor.from_pretrained(SID)
sam = Sam2VideoModel.from_pretrained(SID).to(dev).eval()
print("로드 완료", flush=True)

# 0.5초 간격 60프레임(=30초) 읽기
cap = cv2.VideoCapture(MP4); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
step = max(1, int(round(fps * 0.5)))
frames, times = [], []
start_f = int(191.0 * fps)
cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
i = 0
while len(frames) < 60:
    ok, fr = cap.read()
    if not ok: break
    if i % step == 0:
        frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)); times.append(round(191.0 + len(times) * 0.5, 1))
    i += 1
cap.release()
H, W = frames[0].shape[:2]
print(f"프레임 {len(frames)}장 · {W}x{H} · {times[0]}~{times[-1]}초", flush=True)


def dino(rgb, th=0.25):
    with torch.no_grad():
        inp = gproc(images=rgb, text=PROMPT, return_tensors="pt").to(dev)
        r = gproc.post_process_grounded_object_detection(gd(**inp), inp.input_ids, threshold=th,
                                                          text_threshold=th, target_sizes=[(rgb.shape[0], rgb.shape[1])])[0]
    d = sorted([(float(s), *[float(v) for v in b]) for s, b in zip(r["scores"], r["boxes"])], key=lambda x: -x[0])
    def ov(a, b):
        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy; sa = (a[2]-a[0])*(a[3]-a[1]); sb = (b[2]-b[0])*(b[3]-b[1])
        return (inter/(sa+sb-inter) if sa+sb-inter > 0 else 0, max(inter/sa if sa else 0, inter/sb if sb else 0))
    keep = []
    for x in d:
        if all((lambda v: v[0] < 0.4 and v[1] < 0.9)(ov(x[1:], k[1:])) for k in keep):
            keep.append(x)
    return keep


t0 = time.time()
seeds = dino(frames[0])
print(f"씨앗 프레임 DINO {len(seeds)}개 ({time.time()-t0:.1f}s)", flush=True)
if not seeds:
    print("씨앗 없음 → 중단"); raise SystemExit

t0 = time.time()
sess = sproc.init_video_session(video=frames, inference_device=dev, dtype=torch.bfloat16)
print(f"세션 생성 {time.time()-t0:.1f}s · 타입 {type(sess).__name__}", flush=True)

boxes = [[float(s[1]), float(s[2]), float(s[3]), float(s[4])] for s in seeds]
sproc.add_inputs_to_inference_session(sess, frame_idx=0, obj_ids=list(range(1, len(boxes) + 1)),
                                      input_boxes=[boxes], original_size=(H, W))
print("씨앗 주입 완료", flush=True)

t0 = time.time(); n = 0; per_frame = {}
with torch.no_grad():
    for out in sam.propagate_in_video_iterator(sess):
        idx = int(out.frame_idx)
        m = sproc.post_process_masks(out.pred_masks.cpu(), [(H, W)], binarize=True)[0]
        arr = m.numpy() if hasattr(m, "numpy") else np.asarray(m)
        bxs = []
        for k in range(arr.shape[0]):
            ys, xs = np.nonzero(arr[k] > 0)
            if len(xs) < 20: continue
            bxs.append([float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())])
        per_frame[idx] = bxs; n += 1
el = time.time() - t0
print(f"전파 {n}프레임 · {el:.1f}s · 프레임당 {el/max(n,1)*1000:.0f}ms", flush=True)
hit = sum(1 for v in per_frame.values() if v)
print(f"박스가 나온 프레임 {hit}/{n}")
for i in (0, 10, 30, 59):
    if i in per_frame:
        b = per_frame[i]
        print(f"  프레임 {i} (t={times[i]}s): {len(b)}개" + (f" 첫박스 {[round(x) for x in b[0]]}" if b else ""))

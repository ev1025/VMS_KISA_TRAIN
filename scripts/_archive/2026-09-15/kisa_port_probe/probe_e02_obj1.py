# -*- coding: utf-8 -*-
"""E02_001 객체1(카메라 쪽으로 걸어오는 사람) 전파 진단: 프레임별 SAM 존재점수·마스크 넓이·기준 넓이·게이트 통과 여부를 그대로 찍는다."""
import json, io, sys, numpy as np, torch
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
sys.path.insert(0, V + "/dash_v2")
import serve_kisa as S
CLIP = "aihub_침입쓰러짐영상/쓰러짐/E02_001"
d = json.load(io.open(f"{V}/data/학습데이터/자동라벨/sam2/E02_001.json", encoding="utf-8"))
OBJ = int(sys.argv[1]) if len(sys.argv) > 1 else 1
seeds = sorted([s for s in d["seeds"] if s["obj"] == OBJ], key=lambda s: s["t"])
print("객체", OBJ, "참조샷", [(s["t"], round(s["box"][2] * s["box"][3] * 1280 * 720)) for s in seeds])
t0, t1 = 55.0, 78.5
frames, times, W, H = S._read_frames(CLIP, t0, t1, 0.5)
from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
dev = "cuda"
proc = Sam2VideoProcessor.from_pretrained(S.SAM2V_ID); model = Sam2VideoModel.from_pretrained(S.SAM2V_ID).to(dev).eval()
sess = proc.init_video_session(video=frames, inference_device=dev, dtype=torch.float32)
fidx = lambda t: min(range(len(times)), key=lambda k: abs(times[k] - t))
prof = []
for s in seeds:
    b = s["box"]; bx = [b[0] * W, b[1] * H, (b[0] + b[2]) * W, (b[1] + b[3]) * H]
    proc.add_inputs_to_inference_session(sess, frame_idx=fidx(s["t"]), obj_ids=[OBJ], input_boxes=[[bx]], original_size=(H, W))
    prof.append((s["t"], b[2] * W * b[3] * H))
seed_t = {fidx(s["t"]) for s in seeds}
def area_at(tsec):
    if tsec <= prof[0][0]: return prof[0][1]
    if tsec >= prof[-1][0]: return prof[-1][1]
    for (a0, v0), (a1, v1) in zip(prof, prof[1:]):
        if a0 <= tsec <= a1: return v0 + (v1 - v0) * ((tsec - a0) / (a1 - a0) if a1 > a0 else 0)
    return prof[-1][1]
rows = []
with torch.no_grad():
    for rev in (False, True):
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=min(seed_t), reverse=rev):
            i = int(r.frame_idx)
            sc = r.object_score_logits; scv = None if sc is None else float(sc.detach().flatten()[0])
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while arr.ndim > 2: arr = arr[0]
            bb = S._mask_bbox(arr)
            area = None if bb is None else (bb[2] - bb[0]) * (bb[3] - bb[1])
            sa = area_at(times[i])
            keep = bb is not None and (scv is None or scv > 0) and area <= 0.5 * W * H and area <= 3 * sa and area >= sa / 3
            rows.append((times[i], "seed" if i in seed_t else "", None if scv is None else round(scv, 2), None if area is None else int(area), int(sa), None if bb is None else round((bb[0] + bb[2]) / 2 / W, 2), "keep" if keep else "DROP"))
for row in sorted(rows): print(row)

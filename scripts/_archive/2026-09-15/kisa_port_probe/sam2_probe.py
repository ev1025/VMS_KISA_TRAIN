"""SAM2 점 프롬프트 검증: DINO 박스 중심을 점으로 주고 마스크가 나오는지, 그 마스크에서 뽑은
타이트 박스가 DINO 박스보다 정확한지 본다. 침입 판정이 '네 꼭짓점 중 3개가 구역 안'이라 박스 크기가 곧 점수다."""
import os, sys, torch, cv2, numpy as np, xml.etree.ElementTree as ET
sys.path.insert(0, "/NHNHOME/WORKSPACE/26mss002_E3/vms/_kisa_port/tools")
import kisa_items as K
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection, Sam2Processor, Sam2Model

V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
D = f"{V}/data/원본데이터/kisa_배포_검증영상"
OUT = f"{V}/dumps/kisa_port/sam2"; os.makedirs(OUT, exist_ok=True)
PROMPT = "a person. a pedestrian. a human. a man walking. a person with an umbrella."
dev = "cuda"

gproc = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-base")
gd = AutoModelForZeroShotObjectDetection.from_pretrained("IDEA-Research/grounding-dino-base").to(dev).eval()
SAM_ID = os.environ.get("SAM_ID", "facebook/sam2.1-hiera-small")
sproc = Sam2Processor.from_pretrained(SAM_ID)
sam = Sam2Model.from_pretrained(SAM_ID).to(dev).eval()
print("모델 로드 완료:", SAM_ID, flush=True)

CLIPS = [("침입(30개)", "C00_255_0001", "야간 IR 눈"),
         ("침입(30개)", "C00_275_0001", "야간 설경 원거리"),
         ("배회(30개)", "C00_225_0001", "눈보라"),
         ("침입(30개)", "C00_126_0002", "우천 우산")]


def gt_of(folder, stem):
    r = ET.parse(f"{D}/deploy_val/{folder}/배포/{stem}.xml").getroot().find(".//Alarm")
    h, m, s = r.findtext("StartTime").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def dino(fr, th=0.30):
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = gproc(images=rgb, text=PROMPT, return_tensors="pt").to(dev)
        r = gproc.post_process_grounded_object_detection(gd(**inp), inp.input_ids, threshold=th,
                                                          text_threshold=th, target_sizes=[rgb.shape[:2]])[0]
    d = [(float(s), *[float(v) for v in b]) for s, b in zip(r["scores"], r["boxes"])]

    def iou(a, b):
        ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1]); ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
        return inter / ua if ua > 0 else 0.0
    d.sort(key=lambda x: -x[0]); keep = []
    for x in d:
        if all(iou(x[1:], k[1:]) < 0.5 for k in keep):
            keep.append(x)
    return keep


def sam_mask(fr, point):
    """점 하나로 마스크. 반환 = (마스크 bool, 그 마스크의 타이트 박스)"""
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = sproc(images=rgb, input_points=[[[list(point)]]], input_labels=[[[1]]], return_tensors="pt").to(dev)
        out = sam(**inp, multimask_output=True)
        masks = sproc.post_process_masks(out.pred_masks.cpu(), inp["original_sizes"])[0][0]
        scores = out.iou_scores[0][0].cpu().numpy()
    best = int(np.argmax(scores))
    m = masks[best].numpy().astype(bool)
    ys, xs = np.where(m)
    if len(xs) == 0:
        return m, None, float(scores[best])
    return m, (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())), float(scores[best])


for folder, stem, note in CLIPS:
    g = gt_of(folder, stem)
    cap = cv2.VideoCapture(f"{D}/deploy_val/{folder}/배포/{stem}.mp4"); fps = cap.get(cv2.CAP_PROP_FPS)
    tiles = []
    for t in (g - 4, g - 2, g):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps))); ok, fr = cap.read()
        if not ok:
            continue
        vis = fr.copy(); lines = []
        for sc, x1, y1, x2, y2 in dino(fr)[:3]:
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            m, tb, ms = sam_mask(fr, (cx, cy))
            vis[m] = (0.55 * vis[m] + 0.45 * np.array([255, 120, 0])).astype(np.uint8)   # 마스크 파랑
            cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)   # DINO 초록
            if tb:
                cv2.rectangle(vis, (int(tb[0]), int(tb[1])), (int(tb[2]), int(tb[3])), (0, 255, 255), 2)  # SAM2 노랑
                lines.append(f"DINO {x2-x1:.0f}x{y2-y1:.0f} -> SAM2 {tb[2]-tb[0]:.0f}x{tb[3]-tb[1]:.0f} (iou_score {ms:.2f})")
        cv2.putText(vis, f"{stem} t={t}", (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        for i, ln in enumerate(lines):
            cv2.putText(vis, ln, (10, 52 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        print(f"  {stem} t={t}: " + (" | ".join(lines) if lines else "DINO 박스 없음"), flush=True)
        tiles.append(cv2.resize(vis, (860, 484)))
    if tiles:
        cv2.imwrite(f"{OUT}/{stem}.jpg", np.hstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 84])
print("저장:", OUT)

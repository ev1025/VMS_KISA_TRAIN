# -*- coding: utf-8 -*-
"""SR 재탐지의 진짜 F1 (오탐 포함) 실측. 제미나이 '환각 오탐' 우려를 실측으로 판정.
   전 구간 0.5초 스트라이드, 6뷰 타일. base 스트림 = 타일 conf. SR 스트림 = 약신호 타일(base 0.10~0.40)만
   Real-ESRGAN ×2 → 1280 추론으로 갱신. 두 스트림 각각 규칙(6프레임 중 4 ≥0.4) 온셋 → GT 대조.
   음성(비화재 20편)에서 온셋이 뜨면 오탐."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import kisa_paths as _KP   # 경로는 한 곳에서만 정한다(docs/file_path.md 1절)
import sys, types, xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
import cv2, torch
import torchvision.transforms.functional as F
shim = types.ModuleType("torchvision.transforms.functional_tensor"); shim.__dict__.update(F.__dict__)
sys.modules["torchvision.transforms.functional_tensor"] = shim
from realesrgan import RealESRGANer
from basicsr.archs.rrdbnet_arch import RRDBNet
from ultralytics import YOLO

W = _KP.V.parent; G = _KP.V
STRIDE, DELAY, BEFORE, AFTER = 0.5, 10.0, 2.0, 10.0
LO, HI, TH, WIN, HITS = 0.10, 0.40, 0.40, 6, 4


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(xml):
    if not xml.exists(): return None
    al = ET.parse(xml).getroot().find(".//Alarm")
    return hms(al.findtext("StartTime")) if al is not None else None


def tiles(fr):
    h, w = fr.shape[:2]
    return [fr] + [fr[y:y + h // 2, x:x + w // 2] for x, y in ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]


def fire_conf(model, img, imgsz):
    r = model.predict(img, conf=0.05, verbose=False, imgsz=imgsz)[0]
    return max([float(b.conf) for b in r.boxes if int(b.cls) == 0], default=0.0)


def run(model, sr, mp4):
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps * STRIDE)); i = 0
    wb, ws = deque(maxlen=WIN), deque(maxlen=WIN); on_b = on_s = None; n_sr = 0
    while True:
        if not cap.grab(): break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                t = i / fps; cb = cs = 0.0
                for c in tiles(fr):
                    b = fire_conf(model, c, 640); cb = max(cb, b); s = b
                    if LO <= b < HI:                                  # 약신호 타일만 SR
                        up, _ = sr.enhance(c, outscale=2); s = fire_conf(model, up, 1280); n_sr += 1
                    cs = max(cs, s)
                wb.append((t, cb >= TH)); ws.append((t, cs >= TH))
                if on_b is None and sum(h for _, h in wb) >= HITS: on_b = next(t0 for t0, h in wb if h)
                if on_s is None and sum(h for _, h in ws) >= HITS: on_s = next(t0 for t0, h in ws if h)
        i += 1
    cap.release()
    return on_b, on_s, n_sr


def judge(gt, on):
    if on is None: return "미검" if gt is not None else "정상"
    sa = on + DELAY
    if gt is None: return "오탐"
    return "정검" if gt - BEFORE <= sa <= gt + AFTER else "오탐"


def main():
    model = YOLO(str(G / "model/fire_base.pt"))
    net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    sr = RealESRGANer(scale=4, model_path=str(G / "model/sr/RealESRGAN_x4plus.pth"), model=net, tile=0, half=True, device=torch.device("cuda"))
    vids = [(m, gt_start(W / "vms/data/원본데이터/kisa_배포_방화채점셋/gt" / (m.stem + ".xml"))) for m in sorted((W / "vms/data/원본데이터/kisa_배포_방화채점셋/videos").glob("*.mp4"))]
    vids += [(m, None) for m in sorted((G / "datasets/rnd_rest/5. 싸움(200개)").rglob("*.mp4"))[:20]]
    tally = {"base": {}, "sr": {}}
    print(f"{'영상':16s} {'GT':>6s} {'base온셋':>8s} {'판정':>4s} {'SR온셋':>8s} {'판정':>4s} {'SR호출':>6s}")
    for mp4, gt in vids:
        ob, os_, n = run(model, sr, mp4)
        jb, js = judge(gt, ob), judge(gt, os_)
        tally["base"][jb] = tally["base"].get(jb, 0) + 1; tally["sr"][js] = tally["sr"].get(js, 0) + 1
        print(f"{mp4.stem:16s} {'-' if gt is None else gt:>6} {'-' if ob is None else f'{ob:.1f}':>8} {jb:>4s} {'-' if os_ is None else f'{os_:.1f}':>8} {js:>4s} {n:6d}", flush=True)
    for k, d in tally.items():
        tp, fn, fp = d.get("정검", 0), d.get("미검", 0), d.get("오탐", 0)
        r = tp / (tp + fn) if tp + fn else 0; p = tp / (tp + fp) if tp + fp else 0
        print(f"{k}: 정검 {tp} 미검 {fn} 오탐 {fp} → F1 {2*r*p/(r+p)*100 if r+p else 0:.1f}")


if __name__ == "__main__":
    main()

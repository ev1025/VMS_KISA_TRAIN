# -*- coding: utf-8 -*-
"""Real-ESRGAN 약신호 재탐지 실측: KISA 방화 10편 GT창 안에서
   base(타일, 640) vs 타일→SR×2→1280 추론. 영상별 최대 fire conf 와 0.4 이상 프레임 수 비교."""
import sys, types, xml.etree.ElementTree as ET
from pathlib import Path
import cv2, numpy as np, torch

# basicsr 이 참조하는 구 torchvision 모듈을 런타임 주입 (시스템 경로 읽기전용)
import torchvision.transforms.functional as F
shim = types.ModuleType("torchvision.transforms.functional_tensor"); shim.__dict__.update(F.__dict__)
sys.modules["torchvision.transforms.functional_tensor"] = shim
from realesrgan import RealESRGANer
from basicsr.archs.rrdbnet_arch import RRDBNet
from ultralytics import YOLO

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W / "vms"
VID, GT = W / "vms/data/원본데이터/kisa_배포_방화채점셋/videos", W / "vms/data/원본데이터/kisa_배포_방화채점셋/gt"
STRIDE, BEFORE, AFTER = 0.5, 2.0, 10.0


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(xml):
    al = ET.parse(xml).getroot().find(".//Alarm")
    return hms(al.findtext("StartTime")) if al is not None else None


def tiles(fr):
    h, w = fr.shape[:2]
    return [fr] + [fr[y:y + h // 2, x:x + w // 2] for x, y in
                   ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]


def max_fire(model, img, imgsz):
    r = model.predict(img, conf=0.05, verbose=False, imgsz=imgsz)[0]
    return max([float(b.conf) for b in r.boxes if int(b.cls) == 0], default=0.0)


def main():
    model = YOLO(str(G / "model/fire_base.pt"))
    net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    sr = RealESRGANer(scale=4, model_path=str(G / "model/sr/RealESRGAN_x4plus.pth"),
                      model=net, tile=0, half=True, device=torch.device("cuda"))
    print(f"{'영상':16s} {'base max':>9s} {'base≥.4':>8s} {'SR max':>8s} {'SR≥.4':>6s}  판정")
    tot_b = tot_s = 0
    for mp4 in sorted(VID.glob("*.mp4")):
        gt = gt_start(GT / (mp4.stem + ".xml"))
        if gt is None: continue
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps * STRIDE)); i = 0
        bmax = smax = 0.0; bhit = shit = 0
        while True:
            if not cap.grab(): break
            t = i / fps
            if i % step == 0 and gt - BEFORE <= t <= gt + AFTER:
                ok, fr = cap.retrieve()
                if ok:
                    b = max(max_fire(model, c, 640) for c in tiles(fr))
                    s = 0.0
                    for c in tiles(fr):                      # 타일 → SR ×2 → 1280 추론
                        up, _ = sr.enhance(c, outscale=2)
                        s = max(s, max_fire(model, up, 1280))
                    bmax, smax = max(bmax, b), max(smax, s)
                    bhit += b >= 0.4; shit += s >= 0.4
            if t > gt + AFTER: break
            i += 1
        cap.release()
        verdict = "SR 효과" if shit >= 4 > bhit else ("동일" if (shit >= 4) == (bhit >= 4) else "SR 악화")
        tot_b += bhit >= 4; tot_s += shit >= 4
        print(f"{mp4.stem:16s} {bmax:9.2f} {bhit:8d} {smax:8.2f} {shit:6d}  {verdict}")
    print(f"\n규칙(4프레임≥0.4) 충족 영상: base {tot_b}/10 → SR {tot_s}/10")


if __name__ == "__main__":
    main()

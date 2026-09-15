# -*- coding: utf-8 -*-
"""서버 시작 직후 SAM2(이미지·비디오) 모델을 백그라운드에서 미리 올린다. 재시작 뒤 첫 탭이 1분 넘게 걸리던 것 방지."""
import io, re
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "_warmup_models" not in s
m = re.search(r'\nif __name__ == "__main__":\n', s)
assert m
warm = '''

def _warmup_models():
    """SAM2 이미지·비디오 모델을 미리 GPU 에 올린다(첫 요청 지연 제거). 실패해도 서버는 뜬다."""
    try:
        import torch
        from transformers.models.sam2.processing_sam2 import Sam2Processor
        from transformers.models.sam2.modeling_sam2 import Sam2Model
        global _SAM2
        if _SAM2 is None:
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            _SAM2 = (Sam2Processor.from_pretrained(SAM2_ID), Sam2Model.from_pretrained(SAM2_ID).to(dev).eval(), dev)
    except Exception as e:
        print("[warmup] sam2 image:", e, flush=True)
    try:
        from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
        from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
        global _SAM2V
        if _SAM2V is None:
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            _SAM2V = (Sam2VideoProcessor.from_pretrained(SAM2V_ID), Sam2VideoModel.from_pretrained(SAM2V_ID).to(dev).eval(), dev)
    except Exception as e:
        print("[warmup] sam2 video:", e, flush=True)
    print("[warmup] done", flush=True)
'''
s = s[:m.start()] + warm + s[m.start():]
# main 에서 스레드로 호출
s = re.sub(r'(\nif __name__ == "__main__":\n)', r'\1    threading.Thread(target=_warmup_models, daemon=True).start()\n', s, count=1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")

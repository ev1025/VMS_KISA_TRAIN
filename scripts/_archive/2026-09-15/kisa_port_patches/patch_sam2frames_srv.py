# -*- coding: utf-8 -*-
"""/api/sam2frames : 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지 = 손라벨 ∪ SAM)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "/api/sam2frames" not in s, "이미 적용됨"
old = '        if p == "/api/sam2label":            # SAM 전파 결과 저장소(클립 전체) {frames: {t: {obj: [x,y,w,h]}}, seeds}'
new = '''        if p == "/api/sam2frames":           # 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지용)
            out = {}
            if SAM2_DIR.exists():
                for fj in SAM2_DIR.glob("*.json"):
                    try:
                        fr = json.loads(fj.read_text(encoding="utf-8")).get("frames") or {}
                        ts = sorted(float(k) for k, v in fr.items() if v)
                        if ts:
                            out[fj.stem] = ts
                    except Exception:
                        pass
            self._bytes(json.dumps(out).encode(), "application/json; charset=utf-8")
            return
''' + old
assert s.count(old) == 1
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("server patched")

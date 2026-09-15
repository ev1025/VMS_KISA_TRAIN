# -*- coding: utf-8 -*-
"""정답라벨 저장소(data/학습데이터/정답라벨/<stem>.json) 읽기 API:
/api/gtlabel?clip=  → 그 클립의 정답(박스·점·이벤트), /api/gtframes → {stem: [t,...]}(박스 있는 프레임; 배지·학습 집계용)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "GT_DIR" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:90])
    s = s.replace(old, new, 1)
rep('''SAM2_DIR = G / "data/학습데이터/자동라벨/sam2"''',
    '''SAM2_DIR = G / "data/학습데이터/자동라벨/sam2"
GT_DIR = G / "data/학습데이터/정답라벨"       # 데이터셋이 제공한 정답(박스·점). 사람이 고치면 손라벨로 승격''')
rep('''        if p == "/api/sam2frames":           # 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지용)''',
    '''        if p == "/api/gtlabel":              # 정답라벨 저장소(클립) {frames, points, events, actions}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            f = GT_DIR / (Path((q.get("clip") or [""])[0]).stem + ".json")
            d = {"frames": {}, "points": {}, "events": [], "actions": {}}
            if f.exists():
                try: d = json.loads(f.read_text(encoding="utf-8"))
                except Exception: pass
            self._bytes(json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/gtframes":             # 정답 박스가 있는 프레임 시각 {stem: [t,...]}
            out = {}
            if GT_DIR.exists():
                for fj in GT_DIR.glob("*.json"):
                    try:
                        fr = json.loads(fj.read_text(encoding="utf-8")).get("frames") or {}
                        ts = sorted(float(k) for k, v in fr.items() if v)
                        if ts:
                            out[fj.stem] = ts
                    except Exception:
                        pass
            self._bytes(json.dumps(out).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2frames":           # 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지용)''')
io.open(p, "w", encoding="utf-8").write(s)
print("server ok")

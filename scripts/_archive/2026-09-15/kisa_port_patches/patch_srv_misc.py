# -*- coding: utf-8 -*-
"""서버 정리
1) /dsimg, /dslabel : images/train/<f> 가 없으면 images/<f> (labels 도 같이) — train 하위 폴더 없는 학습셋(aihub71751_24k)
2) _stream Range: 'bytes=-500' 같은 접미 범위·이상한 헤더에서 예외 대신 전체 전송
3) /api/meta, /api/dataset : 파일 없으면 404 (스레드 예외 대신)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new, 1)

rep('''        m = re.match(r"/dsimg/(.+)$", p)
        if m:
            ip = G/urllib.parse.unquote(m.group(1))
            if ip.exists() and WS in ip.resolve().parents:''',
'''        m = re.match(r"/dsimg/(.+)$", p)
        if m:
            ip = G/urllib.parse.unquote(m.group(1))
            if not ip.exists() and "/images/train/" in ip.as_posix():
                ip = Path(ip.as_posix().replace("/images/train/", "/images/"))   # train 하위 폴더 없이 images/ 에 바로 있는 세트
            if ip.exists() and WS in ip.resolve().parents:''')
rep('''        m = re.match(r"/dslabel/(.+\\.txt)$", p)
        if m:
            lp = G/urllib.parse.unquote(m.group(1))
            if lp.exists() and WS in lp.resolve().parents:''',
'''        m = re.match(r"/dslabel/(.+\\.txt)$", p)
        if m:
            lp = G/urllib.parse.unquote(m.group(1))
            if not lp.exists() and "/labels/train/" in lp.as_posix():
                lp = Path(lp.as_posix().replace("/labels/train/", "/labels/"))
            if lp.exists() and WS in lp.resolve().parents:''')
rep('''        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\\d+)-(\\d*)", rng)
            start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size-1''',
'''        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\\d+)-(\\d*)", rng) if rng else None
        if rng and not m:
            rng = None                                   # 접미 범위(bytes=-N) 등은 지원 안 함 → 전체 전송
        if rng:
            start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size-1
            if start >= size:
                self.send_error(416); return''')
rep('''        if p == "/api/meta":
            self._stream(HERE/"dash_meta.json", "application/json; charset=utf-8"); return
        if p == "/api/dataset":
            self._stream(HERE/"dataset_meta.json", "application/json; charset=utf-8"); return''',
'''        if p == "/api/meta":
            f = HERE/"dash_meta.json"
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404, "dash_meta.json 없음"); return
        if p == "/api/dataset":
            f = HERE/"dataset_meta.json"
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404, "dataset_meta.json 없음"); return''')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")

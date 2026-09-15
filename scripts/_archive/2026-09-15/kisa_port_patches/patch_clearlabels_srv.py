# -*- coding: utf-8 -*-
"""/api/clearlabels (POST {clip, kind}) : 그 클립의 학습 프레임 초기화 = 손라벨 행 전부 삭제(백업 뒤) + SAM 전파 저장소 비움."""
import io
import pathlib; p = str(pathlib.Path(__file__).resolve().parents[1] / "dash_v2/serve_kisa.py")
s = io.open(p, encoding="utf-8").read()
assert "/api/clearlabels" not in s
old = '''        if p == "/api/savelabel":
            _SAVE_LOCK.acquire()'''
new = '''        if p == "/api/clearlabels":           # 학습 프레임 초기화: 클립의 손라벨 전부 삭제(백업) + SAM 저장소 비움
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                clip = Path(body["clip"]).stem
                fn = "person_labels.json" if body.get("kind") == "person" else "fire_labels.json"
                fl = data_path("data/학습데이터/손라벨/" + fn, fn)
                with _SAVE_LOCK:
                    _backup_labels(fl)
                    rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                    keep = [r for r in rows if r.get("clip") != clip]
                    removed = len(rows) - len(keep)
                    tmp = fl.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(fl)
                sam_n = sam2_store_clear(body["clip"])
                self._bytes(json.dumps({"ok": True, "hand_rows": removed, "sam_frames": sam_n}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/savelabel":
            _SAVE_LOCK.acquire()'''
assert s.count(old) == 1
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("server ok")

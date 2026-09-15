# -*- coding: utf-8 -*-
"""손라벨 박스 프레임과 SAM 프레임을 서로 겹치지 않게 한다(미리보기·라벨 검수·편집기 불일치의 뿌리).
 규칙: 손라벨 박스가 있는 프레임 = 손라벨만(SAM 저장소에서 제거·전파도 건너뜀).
       빈 라벨(cls -1, 검토완료) 프레임 = DINO 프리필만 막고 SAM 결과는 보인다(전파가 더 나중 의도).
클라이언트: 저장 직후 SAMMAP 에서 그 프레임 제거, 빈 라벨 프레임에 SAM 얹기 허용."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "손라벨이 SAM 을 대신" not in s
def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:90])
    s = s.replace(old, new)
# 1) 저장 직후: 그 프레임의 SAM 결과는 클라이언트 캐시에서도 뺀다(서버는 savelabel 에서 뺀다)
rep("""      const res = await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);
      f.saved = LB.boxes.map(b => b.slice()); LB.src = "hand";""",
    """      const res = await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);
      f.saved = LB.boxes.map(b => b.slice()); LB.src = "hand";
      const sk = Number(f.t).toFixed(1);                 // 손라벨이 SAM 을 대신: 같은 프레임의 SAM 결과는 캐시에서 뺀다(서버 저장소는 savelabel 이 뺐다)
      if (SAMMAP[f.clip] && SAMMAP[f.clip][sk]) { delete SAMMAP[f.clip][sk]; SAML[f.clip] = Promise.resolve(SAMMAP[f.clip]); SAMFR[f.stem] = samFramesOf(f.clip); SM.propFrames = SAMFR[f.stem].map(t => Number(t).toFixed(1)); if (typeof updateRawBadge === "function") updateRawBadge(f.stem); }""")
# 2) 빈 라벨(검토완료) 프레임: DINO/정답 프리필은 막되 SAM 결과는 얹는다
rep("""  const wantPseudo = (LB.mode === "person" && !saved);       // 손라벨이 없을 때만 의사라벨을 얹는다""",
    """  const wantPseudo = (LB.mode === "person" && !(saved && saved.length));   // 손라벨 박스가 없을 때만 의사라벨. 빈 라벨(검토완료) 프레임은 SAM 만 얹는다""")
rep("""      if (!bx.length) { bx = gtBoxesAt(gt, sec).map(b => b.slice(0, 5)); src = "gt"; }
      if (!bx.length) { bx = autoBoxesAt(dino, sec); src = "dino"; }""",
    """      if (!bx.length && !saved) { bx = gtBoxesAt(gt, sec).map(b => b.slice(0, 5)); src = "gt"; }   // 빈 라벨 프레임엔 정답·DINO 안 얹는다
      if (!bx.length && !saved) { bx = autoBoxesAt(dino, sec); src = "dino"; }""")
rep("""  if (!LB.src) LB.src = f.saved ? "hand" : "none";""",
    """  if (!LB.src) LB.src = (f.saved && f.saved.length) ? "hand" : "none";""")
rep("""    if (LB.src === "sam" || (!f.saved && !LB.boxes.length)) { const bx = samBoxesAt(sam, f.t);""",
    """    if (LB.src === "sam" || (!(f.saved && f.saved.length) && !LB.boxes.length)) { const bx = samBoxesAt(sam, f.t);""")
rep("""      if (LB.sec !== sec || LB.boxes.length || f.saved || LB.src === "hand") return;   // 손라벨(빈 라벨 포함)로 확정된 프레임엔 안 얹는다""",
    """      if (LB.sec !== sec || LB.boxes.length || (f.saved && f.saved.length) || LB.src === "hand") return;   // 손라벨 박스로 확정된 프레임엔 안 얹는다(빈 라벨 프레임엔 SAM 만 온다)""")
rep("""      LB.boxes = saved ? saved.map(b => b.slice()) : []; LB.src = saved ? "hand" : "none";""",
    """      LB.boxes = saved ? saved.map(b => b.slice()) : []; LB.src = (saved && saved.length) ? "hand" : "none";""")
io.open(p, "w", encoding="utf-8").write(s)
print("editor.js ok")

p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "_hand_box_frames" not in s
# 3) 전파 결과 저장: 손라벨 박스가 있는 프레임은 건너뛴다
rep("""    d.setdefault("frames", {}); d.setdefault("seeds", [])
    for t, objs in (frames or {}).items():
        k = f"{float(t):.1f}"; cur = d["frames"].get(k)""",
    """    d.setdefault("frames", {}); d.setdefault("seeds", [])
    hand = _hand_box_frames(clip)                     # 손라벨 박스가 있는 프레임은 손라벨만(SAM 결과는 버린다)
    for t, objs in (frames or {}).items():
        k = f"{float(t):.1f}"; cur = d["frames"].get(k)
        if k in hand:
            continue""")
rep("""def sam2_store_drop(clip, t):
    f = SAM2_DIR / (Path(clip).stem + ".json")""",
    """def _hand_box_frames(clip):
    \"\"\"그 클립에서 손라벨 박스(cls>=0)가 있는 프레임 키("190.5") 집합. 사람·화재 손라벨 파일 둘 다 본다.\"\"\"
    stem = Path(clip).stem; out = set()
    for fn in ("person_labels.json", "fire_labels.json"):
        fl = data_path("data/학습데이터/손라벨/" + fn, fn)
        try:
            rows = json.loads(fl.read_text(encoding="utf-8")) if fl.exists() else []
        except Exception:
            rows = []
        for r in rows:
            if Path(str(r.get("clip", ""))).stem == stem and int(r.get("cls", -1)) >= 0:
                out.add(f"{round(float(r.get('t', 0)) * 2) / 2:.1f}")
    return out


def sam2_store_drop(clip, t):
    f = SAM2_DIR / (Path(clip).stem + ".json")""")
# 4) 손라벨 저장(박스든 빈 라벨이든) → 그 프레임을 SAM 저장소에서 뺀다. 같은 락 안이라 감싸지 않은 원본을 부른다
rep("""sam2_store_drop = _locked_store(sam2_store_drop)""",
    """_sam2_store_drop_raw = sam2_store_drop            # savelabel 은 이미 _SAVE_LOCK 안 → 락 없는 원본으로
sam2_store_drop = _locked_store(sam2_store_drop)""")
rep("""                tmp = fl.with_suffix(f".json.tmp{os.getpid()}")   # 다른 프로세스가 같은 임시이름을 쓰면 내용이 섞인다
                json.dump(rows, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                tmp.replace(fl)""",
    """                tmp = fl.with_suffix(f".json.tmp{os.getpid()}")   # 다른 프로세스가 같은 임시이름을 쓰면 내용이 섞인다
                json.dump(rows, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                tmp.replace(fl)
                try:
                    _sam2_store_drop_raw(clip, t)                 # 손라벨이 SAM 을 대신: 이 프레임의 전파 결과는 저장소에서 뺀다
                except Exception:
                    pass""")
io.open(p, "w", encoding="utf-8").write(s)
print("serve_kisa.py ok")

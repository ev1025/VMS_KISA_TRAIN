# -*- coding: utf-8 -*-
"""1) 박스의 소유 객체를 인덱스가 아니라 위치(IoU)로 찾는다 — 손라벨 참조로 만든 참조샷의 인덱스가 화면 박스 순서와 어긋나
   다른 객체 박스를 조절하면 현재 객체로 번호가 바뀌던 것.
2) 객체 삭제 = 그 객체의 참조샷과 박스(현재 프레임 + 다른 프레임 손라벨)까지 지운다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "seedForBox" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)

# 헬퍼: dropUnownedPrefill 앞에
rep("""  const dropUnownedPrefill = () => {               // 프리필(DINO·SAM 저장소) 프레임에서 탭했으면 객체가 잡은 박스만 남긴다(나머지는 손라벨로 안 넘김)""",
    """  const iou4 = (a, b) => { const x1 = Math.max(a[0], b[0]), y1 = Math.max(a[1], b[1]), x2 = Math.min(a[0] + a[2], b[0] + b[2]), y2 = Math.min(a[1] + a[3], b[1] + b[3]); const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1); return inter / (a[2] * a[3] + b[2] * b[3] - inter || 1); };
  const seedForBox = i => {                        // 이 프레임에서 LB.boxes[i] 를 잡고 있는 참조샷: 위치(IoU) 우선, 없으면 인덱스
    const b = LB.boxes[i]; if (!b) return null;
    const here = SM.seeds.filter(q => Math.abs(q.t - f.t) < 0.01);
    let best = null, bi = 0.3;
    here.forEach(q => { const v = iou4(q.box, [b[1], b[2], b[3], b[4]]); if (v > bi) { bi = v; best = q; } });
    return best || here.find(q => q.i === i) || null;
  };
  const dropUnownedPrefill = () => {               // 프리필(DINO·SAM 저장소) 프레임에서 탭했으면 객체가 잡은 박스만 남긴다(나머지는 손라벨로 안 넘김)""")
# dropUnownedPrefill 도 위치 기준으로
rep("""    const own = SM.seeds.filter(q => Math.abs(q.t - f.t) < 0.01 && q.i != null);
    const keep = new Set(own.map(q => q.i));
    const map = {}; let k = 0;
    LB.boxes = LB.boxes.filter((b, i) => { if (keep.has(i)) { map[i] = k++; return true; } return false; });
    own.forEach(q => { q.i = map[q.i]; });""",
    """    const keepIdx = []; LB.boxes.forEach((b, i) => { const q = seedForBox(i); if (q) { keepIdx.push(i); q.i = keepIdx.length - 1; } });
    LB.boxes = keepIdx.map(i => LB.boxes[i]);""")
# seedFromBox: 소유자 = 위치로
rep("""    const owner = SM.seeds.find(q => Math.abs(q.t - f.t) < 0.01 && q.i === i);
    if (owner) { owner.box = box; owner.poly = []; if (owner.obj === SM.cur) SMASK = { box, poly: [] }; drawObjs(); }""",
    """    const owner = seedForBox(i);
    if (owner) { owner.box = box; owner.poly = []; owner.i = i; if (owner.obj === SM.cur) SMASK = { box, poly: [] }; drawObjs(); }""")
# draw 의 색 소유자
rep("""    const ownerOf = i => { if (LAB !== "sam") return null; const q = SM.seeds.find(q => Math.abs(q.t - f.t) < 0.01 && q.i === i); return q ? samCol(q.obj) : null; };   // SAM: 객체가 잡은 박스는 객체 색""",
    """    const ownerOf = i => { if (LAB !== "sam") return null; const q = seedForBox(i); return q ? samCol(q.obj) : null; };   // SAM: 객체가 잡은 박스는 객체 색""")
# Del 의 소유자
rep("""          const owner = SM.seeds.find(q => Math.abs(q.t - f.t) < 0.01 && q.i === i);
          LB.boxes.splice(i, 1); sel = null;""",
    """          const owner = seedForBox(i);
          LB.boxes.splice(i, 1); sel = null;""")
# 탭의 '다른 객체 박스' 판정
rep("""    const claimed = new Set(SM.seeds.filter(q => Math.abs(q.t - t) < 0.01 && q.obj !== SM.cur && q.i != null).map(q => q.i));   // 다른 객체의 박스""",
    """    const claimed = new Set(LB.boxes.map((b, i) => i).filter(i => { const q = seedForBox(i); return q && q.obj !== SM.cur; }));   // 다른 객체의 박스""")
# 객체 삭제: 참조샷 + 박스(현재 프레임·다른 프레임 손라벨)
rep("""del.onclick = () => { SM.objs = SM.objs.filter(q => q !== o); SM.seeds = SM.seeds.filter(q => q.obj !== o); if (SM.cur === o) SM.cur = SM.objs[0]; loadSam(); };""",
    """del.onclick = async () => {
        const mine = SM.seeds.filter(q => q.obj === o);
        if (!confirm(`객체 ${o}의 참조샷 ${mine.length}개와 그 박스를 지웁니다. 계속할까요?`)) return;
        snap();
        const cur = mine.find(q => Math.abs(q.t - f.t) < 0.01);
        if (cur) { const i = LB.boxes.findIndex((b, k) => seedForBox(k) === cur); if (i >= 0) { LB.boxes.splice(i, 1); SM.seeds.forEach(q => { if (Math.abs(q.t - f.t) < 0.01 && q.i != null && q.i > i) q.i -= 1; }); } SP = []; SMASK = null; }
        SM.objs = SM.objs.filter(q => q !== o); SM.seeds = SM.seeds.filter(q => q.obj !== o); if (SM.cur === o) SM.cur = SM.objs[0];
        for (const q of mine) {                        // 다른 프레임: 손라벨에서 그 박스만 뺀다
          if (Math.abs(q.t - f.t) < 0.01) continue;
          const hb = existingBoxes(f.stem, q.t); if (!hb || !hb.length) continue;
          const keep = hb.filter(b => iou4([b[1], b[2], b[3], b[4]], q.box) < 0.7);
          if (keep.length !== hb.length) { try { await postLabel(f.stem, q.t, f.W, f.H, keep, f.src); } catch (e) {} }
        }
        loadSam(); draw(); if (cur) saveNow(); else fillShots();
      };""")
# 객체 번호 글자를 박스 밖(위)으로. 위 여백이 없으면 박스 아래
rep("""        s += `<text x="${sd.box[0] * f.W + 4}" y="${sd.box[1] * f.H + 16}" fill="${cc}" font-size="16" font-weight="800">${sd.obj}</text>`;""",
    """        { const bx = sd.box[0] * f.W + 2, by = sd.box[1] * f.H; s += `<text x="${bx}" y="${by >= 18 ? by - 4 : (sd.box[1] + sd.box[3]) * f.H + 16}" fill="${cc}" font-size="16" font-weight="800">${sd.obj}</text>`; }""")
rep("""        if (SMASK.box) s += `<text x="${SMASK.box[0] * f.W + 4}" y="${SMASK.box[1] * f.H + 16}" fill="${cc}" font-size="16" font-weight="800">${SM.cur}</text>`;""",
    """        if (SMASK.box) { const bx = SMASK.box[0] * f.W + 2, by = SMASK.box[1] * f.H; s += `<text x="${bx}" y="${by >= 18 ? by - 4 : (SMASK.box[1] + SMASK.box[3]) * f.H + 16}" fill="${cc}" font-size="16" font-weight="800">${SM.cur}</text>`; }""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")

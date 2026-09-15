# -*- coding: utf-8 -*-
"""손라벨 참조 번호 배정 v3: 위치(속도 예측) + 외형(박스 색 히스토그램) + 좌우 순서 유지 벌점을 합친 총비용 최소 짝지음.
사람이 교차(검은 옷이 회색 옷 앞을 지나감)해도 색으로 가르고, 무리 이동은 순서로 가른다. 박스·객체가 7개 이하면 모든 짝지음을 다 본다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
assert "외형(색 히스토그램)" not in s
i = s.index("    SM.handRef = true; styleHand();\n    const frames = shotSecs(f.stem)")
j_mark = "    SM.objs.sort((a, b) => a - b); SM.seeds.sort((a, b) => a.t - b.t || a.obj - b.obj);"
j = s.index(j_mark, i)
assert 0 < i < j
new = r'''    SM.handRef = true; styleHand();
    const frames = shotSecs(f.stem).map(([t]) => t).filter(t => (SM.a == null || t >= SM.a) && (SM.b == null || t <= SM.b));
    // 외형(색 히스토그램): 프레임 썸네일을 받아 박스 영역의 색 분포를 잰다 — 교차·무리 이동에서 위치만으로 못 가르는 신원을 가른다
    const hists = {};
    if (LB.mode !== "fire" && frames.length) {
      bHand.disabled = true; pstat.innerHTML = spin(0);
      try {
        await fetch(`/api/warmframes?w=320&clip=${encodeURIComponent(f.clip)}&ts=${frames.join(",")}`).catch(() => {});
        const cv = document.createElement("canvas"); cv.width = 32; cv.height = 32; const g2 = cv.getContext("2d", { willReadFrequently: true });
        const loadImg = u => new Promise(res => { const g = new Image(); g.onload = () => res(g); g.onerror = () => res(null); g.src = u; });
        let n = 0;
        for (const t of frames) {
          const g = await loadImg(`/frameat?clip=${encodeURIComponent(f.clip)}&t=${t}&w=320`);
          const bx = existingBoxes(f.stem, t) || [];
          hists[t] = bx.map(b => {
            if (!g) return null;
            try {
              g2.drawImage(g, b[1] * g.naturalWidth, b[2] * g.naturalHeight, Math.max(1, b[3] * g.naturalWidth), Math.max(1, b[4] * g.naturalHeight), 0, 0, 32, 32);
              const d = g2.getImageData(0, 0, 32, 32).data; const h = new Float32Array(64);
              for (let q = 0; q < d.length; q += 4) h[(d[q] >> 6) * 16 + (d[q + 1] >> 6) * 4 + (d[q + 2] >> 6)] += 1;
              for (let k = 0; k < 64; k++) h[k] /= 1024;
              return h;
            } catch (e) { return null; }
          });
          n++; pstat.innerHTML = spin(Math.round(n / frames.length * 100));
        }
      } catch (e) {}
      bHand.disabled = false; pstat.innerHTML = "";
    }
    const sim = (a, b) => { if (!a || !b) return null; let v = 0; for (let k = 0; k < 64; k++) v += Math.min(a[k], b[k]); return v; };
    let nextObj = SM.seeds.length ? Math.max.apply(null, SM.objs) : 0;
    const last = {};                                  // 객체 → 마지막 위치·속도·외형. 이미 찍은 참조샷으로 초기화
    SM.seeds.slice().sort((a, b) => a.t - b.t).forEach(q => { last[q.obj] = { cx: q.box[0] + q.box[2] / 2, cy: q.box[1] + q.box[3] / 2, t: q.t, vx: 0, vy: 0, app: null }; });
    frames.forEach(t => {
      const boxes = existingBoxes(f.stem, t) || [];
      if (!boxes.length) return;
      const iou = (a, b) => { const x1 = Math.max(a[1], b[1]), y1 = Math.max(a[2], b[2]), x2 = Math.min(a[1] + a[3], b[1] + b[3]), y2 = Math.min(a[2] + a[4], b[2] + b[4]); const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1); return inter / (a[3] * a[4] + b[3] * b[4] - inter || 1); };
      const taken = [], cand = [];
      boxes.forEach((b, i) => { if (taken.some(q => iou(q, b) > 0.7)) return; taken.push(b); cand.push({ b, i, cx: b[1] + b[3] / 2, cy: b[2] + b[4] / 2, hist: (hists[t] || [])[i] || null, obj: null }); });
      if (LB.mode === "fire") cand.forEach(c => { c.obj = c.b[0] === 1 ? 2 : 1; });   // 화재: 클래스가 곧 객체
      else {
        const ks = Object.keys(last).map(Number);
        const cost = (c, k) => {                      // 위치(예측 위치와의 거리/허용거리) + 외형(1 - 색 유사도)
          const q = last[k], dt = Math.max(0, t - q.t), dtp = Math.min(dt, 2);
          const px = q.cx + (q.vx || 0) * dtp, py = q.cy + (q.vy || 0) * dtp;
          const tol = Math.min(0.3, 0.08 + 0.03 * dt), d = Math.hypot(px - c.cx, py - c.cy);
          if (d >= tol) return Infinity;
          const sv = sim(c.hist, q.app);
          return d / tol + (sv == null ? 0 : 0.8 * (1 - sv));
        };
        let assigned = null;
        if (ks.length && cand.length * ks.length <= 30) {     // 작으면 모든 짝지음을 다 보고 총비용 최소(새 객체 = 비용 1, 좌우 순서 뒤집힘 = 쌍마다 +0.15)
          const m = cand.map(c => ks.map(k => cost(c, k)));
          let best = Infinity, bestA = null;
          const inv = cur => { let n = 0; for (let a = 0; a < cur.length; a++) for (let b = a + 1; b < cur.length; b++) { if (cur[a] < 0 || cur[b] < 0) continue; if ((cand[a].cx - cand[b].cx) * (last[ks[cur[a]]].cx - last[ks[cur[b]]].cx) < 0) n++; } return n; };
          const rec = (ci, used, acc, cur) => {
            if (acc >= best) return;
            if (ci === cand.length) { const tot = acc + 0.15 * inv(cur); if (tot < best) { best = tot; bestA = cur.slice(); } return; }
            cur.push(-1); rec(ci + 1, used, acc + 1.0, cur); cur.pop();
            for (let kj = 0; kj < ks.length; kj++) { if (used.has(kj) || !isFinite(m[ci][kj])) continue; used.add(kj); cur.push(kj); rec(ci + 1, used, acc + m[ci][kj], cur); cur.pop(); used.delete(kj); }
          };
          rec(0, new Set(), 0, []);
          if (bestA) assigned = bestA.map(kj => kj < 0 ? null : ks[kj]);
        }
        if (assigned) cand.forEach((c, ci) => { c.obj = assigned[ci]; });
        else {                                        // 크면 가까운(비용 낮은) 순 확정
          const pairs = [];
          cand.forEach((c, ci) => ks.forEach(k => { const v = cost(c, k); if (isFinite(v)) pairs.push({ ci, k, v }); }));
          pairs.sort((x, y) => x.v - y.v); const usedObj = new Set();
          pairs.forEach(pr => { const c = cand[pr.ci]; if (c.obj != null || usedObj.has(pr.k)) return; c.obj = pr.k; usedObj.add(pr.k); });
        }
        cand.forEach(c => { if (c.obj == null) c.obj = ++nextObj; });   // 어느 객체와도 안 맞으면 새 객체
      }
      cand.forEach(c => {
        const obj = c.obj, b = c.b, i = c.i;
        if (!SM.objs.includes(obj)) SM.objs.push(obj);
        const q0 = last[obj], dt0 = q0 ? t - q0.t : 0;
        let app = c.hist;
        if (q0 && q0.app && c.hist) { app = new Float32Array(64); for (let k = 0; k < 64; k++) app[k] = 0.6 * q0.app[k] + 0.4 * c.hist[k]; }   // 외형은 서서히 갱신
        else if (q0 && q0.app && !c.hist) app = q0.app;
        last[obj] = { cx: c.cx, cy: c.cy, t, vx: q0 && dt0 > 0 ? (c.cx - q0.cx) / dt0 : 0, vy: q0 && dt0 > 0 ? (c.cy - q0.cy) / dt0 : 0, app };
        SM.seeds = SM.seeds.filter(q => !(Math.abs(q.t - t) < 0.01 && q.obj === obj));
        SM.seeds.push({ t, obj, box: [b[1], b[2], b[3], b[4]], poly: [], pts: [], i, fromHand: true });
      });
    });
'''
s = s[:i] + new + s[j:]
old = "  bHand.onclick = () => {                            // 토글: 켜면 손라벨 → 참조샷(구간 안 전부), 다시 누르면 그때 넣은 참조샷만 제거"
assert s.count(old) == 1, "onclick 앵커"
s = s.replace(old, "  bHand.onclick = async () => {                      // 토글: 켜면 손라벨 → 참조샷(구간 안 전부), 다시 누르면 그때 넣은 참조샷만 제거", 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")

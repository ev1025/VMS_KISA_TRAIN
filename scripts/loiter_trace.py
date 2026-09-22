# -*- coding: utf-8 -*-
"""배회 판정기(LoiterRule)가 한 편에서 내린 결정을 시각순으로 찍는다. 덤프만 쓴다. 제출 도구는 고치지 않고 감싸서 기록만 한다.

왜 (2026-09-18)
    손라벨 모델은 중복 박스를 정리해도 211·260 편에서 경보가 12초쯤 이르다. 지연(delay)을 늘려도 안 고쳐진다.
    그러면 '뒤에 들어온 진짜 마지막 사람' 이 어느 조건에서 거절됐는지를 봐야 한다.
    LoiterRule._take 의 조건 다섯 개(이어짐 · 고른 사람이 아직 안 · 20초 안 · 한산 · 방금 도착)를 하나씩 찍는다.

사용
    python scripts/loiter_trace.py <덤프폴더> <편> [--dedupe 0.5]
"""
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K      # noqa: E402
import loiter_rule4 as L    # noqa: E402

CFG = K.ITEMS["loitering"]


class Traced(K.LoiterRule):
    def _take(self, t, pid, n):
        ok = super()._take(t, pid, n)
        ct, cpid = self.cur
        c = [t - ct <= self.settle, self.lastseen.get(cpid, -1e9) >= t - self.still_in, t - ct <= self.maxgap,
             n <= self.crowd, abs(self.entry[pid] - self.first_in[pid]) <= self.step]
        why = "" if c[0] else ("  조건: 고른이 아직 안=%s · 20초내=%s · 한산(%d<=%d)=%s · 방금도착(진입 %.1f = 첫봄 %.1f)=%s"
                              % (c[1], c[2], n, self.crowd, c[3], self.entry[pid], self.first_in[pid], c[4]))
        print("  t=%6.1f 새 배회자 트랙%-3s 진입 %.1f → %s (고른 트랙%s 확정 %.1f%s)%s"
              % (t, pid, self.entry[pid], "받음(마지막 사람 교체)" if ok else "거절", cpid, ct,
                 " · 바로 이어짐" if c[0] else "", why))
        return ok

    def feed(self, t, boxes):
        cur0, settled0, loit0 = self.cur, self.settled, set(self.loit)
        r = super().feed(t, boxes)
        if cur0 is None and self.cur is not None:
            print("  t=%6.1f 첫 배회자 트랙%s 진입 %.1f (체류 %.0f초 채움)" % (t, self.cur[1], self.entry[self.cur[1]], self.dwell_s))
        if settled0 is None and self.settled is not None:
            print("  t=%6.1f 확정 → 경보 %.1f + %.0f = %.1f" % (t, self.settled, CFG["delay"], self.settled + CFG["delay"]))
        return r


def main():
    dump, stem = sys.argv[1], sys.argv[2]
    dd = float(sys.argv[sys.argv.index("--dedupe") + 1]) if "--dedupe" in sys.argv else 0.0
    rows, poly, gt = L.load(dump)
    rows, poly, g = rows[stem], poly[stem], gt[stem]
    print("== %s  %s  정답 %s (창 %.1f~%.1f)  dedupe %.1f" % (Path(dump).name, stem, g, g - 2, g + 10, dd))
    j = Traced(poly, CFG["conf"], CFG["corners"], CFG["dwell"], CFG["settle"], CFG["gap"], CFG["stride"],
               CFG["maxgap"], CFG["crowd"], CFG["still_in"])
    for r in rows:
        j.feed(r["t"], L.dedupe_boxes(r["boxes"], dd) if dd else r["boxes"])
    v = j.final()
    print("  최종 경보 %s" % (("%.1f" % (v + CFG["delay"])) if v is not None else "없음"))


if __name__ == "__main__":
    main()

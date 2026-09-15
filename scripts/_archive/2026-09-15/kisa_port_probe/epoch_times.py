# -*- coding: utf-8 -*-
"""실험별 학습 시간: 장수 · 도달 에폭 · 에폭당 중앙값(분) · 누적 시간(h). results.csv 의 time 열(누적 초) 차분."""
import csv, io, glob, os
print("%-34s %8s %6s %8s %8s" % ("실험", "장수", "에폭", "분/에폭", "누적h"))
for f in sorted(glob.glob("runs/*/*/results.csv")):
    n = f.split("/")[1]
    rows = list(csv.DictReader(io.open(f, encoding="utf-8")))
    if len(rows) < 3:
        continue
    t = [float(r["time"]) for r in rows]
    per = [(t[i] - t[i - 1]) / 60 for i in range(1, len(t))]
    per = [x for x in per if 0 < x < 300]                 # 재개 지점의 음수·튄 값 제외
    med = sorted(per)[len(per) // 2] if per else 0
    tr = "_exp/%s/train.txt" % n
    nimg = (sum(1 for _ in open(tr)) - 1) if os.path.exists(tr) else 0
    print("%-34s %8d %6d %8.1f %8.1f" % (n, nimg, len(rows), med, t[-1] / 3600))

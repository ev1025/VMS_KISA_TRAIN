# -*- coding: utf-8 -*-
"""배회: 세 모델(배포·손라벨 32.6%·손라벨 10.8%)에 '같은 규칙 하나' 를 넣었을 때의 표. 채점 경로(BoT-SORT) 덤프만 쓴다.

왜: loiter_rule4 의 '최고' 는 모델마다 다른 조합이 뽑힌다. 실제로는 규칙을 하나만 배포하므로
    후보 몇 개를 고정해 세 모델에 똑같이 넣어 본다. 배포 모델(96.55)이 떨어지면 안 된다.
사용: python scripts/loiter_rule4_common.py [라벨=덤프폴더 ...]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loiter_rule4 as L

DUMPS = [("배포 v2", "dumps/loiter_botsort_v2"), ("손라벨 32.6%", "dumps/loiter_p1280hand_bs1280"),
         ("손라벨 10.8%", "dumps/loiter_p1280ov2_bs1280")]
if len(sys.argv) > 1:
    DUMPS = [tuple(x.split("=", 1)) for x in sys.argv[1:]]
N = L.NOW
CANDS = [("지금 규칙", N),
         ("끊김 10", dict(N, gap=10)),
         ("끊김 10 + 발끝 10px", dict(N, gap=10, margin=10)),
         ("끊김 10 + 발끝 20px", dict(N, gap=10, margin=20)),
         ("끊김 10 + 발끝 40px", dict(N, gap=10, margin=40)),
         ("발끝 10px 만", dict(N, margin=10)),
         ("conf 0.35 + 끊김 10 + 발끝 10px", dict(N, conf_th=0.35, gap=10, margin=10)),
         ("체류 4 + 끊김 10", dict(N, dwell=4.0, gap=10)),
         ("체류 4 + 끊김 10 + 발끝 10px", dict(N, dwell=4.0, gap=10, margin=10))]

data = {}
for label, d in DUMPS:
    rows, poly, gt = L.load(d)
    if rows:
        data[label] = (rows, poly, gt)
print("%-32s" % "규칙(다른 값은 지금 값)" + "".join("  %-30s" % l for l in data))
for name, kw in CANDS:
    line = "%-32s" % name
    for label, (rows, poly, gt) in data.items():
        r = L.run(rows, poly, gt, lambda s, kw=kw: L.sa_entry(rows[s], poly[s], **kw))
        line += "  %6.2f (%2d/%d/%d) 여유 %.1f      " % (r["score"], r["tp"], r["fn"], r["fp"], r["edge"])
    print(line)
print("\n(점수 (맞음/놓침/오검), 여유 = 창 가장자리까지 최소 초. 지금 규칙 = conf %.2f 체류 %.0f 끊김 %d 대기 %.0f delay %.0f)"
      % (N["conf_th"], N["dwell"], N["gap"], N["settle"], N["delay"]))

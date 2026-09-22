# -*- coding: utf-8 -*-
"""세 모델(배포·손라벨 32.6%·손라벨 10.8%)에 '같은 규칙 하나' 를 넣었을 때의 표. 덤프만 쓴다.

왜: intr_rule4 의 '최고' 는 모델마다 다른 조합이 뽑힌다. 실제로는 규칙을 하나만 배포하므로
    후보 조합 몇 개를 고정해 세 모델에 똑같이 넣어 본다. 배포 모델(94.74)이 떨어지면 안 된다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import intr_rule4 as R

DUMPS = [("배포 tile_v3", "dumps/intrusion_tile_v3"), ("손라벨 32.6%", "dumps/intrusion_p1280hand_1280"),
         ("손라벨 10.8%", "dumps/intrusion_p1280ov2_1280")]
if len(sys.argv) > 1:                      # 사용: intr_rule4_common.py 라벨=덤프폴더 [라벨=덤프폴더 ...]
    DUMPS = [tuple(x.split("=", 1)) for x in sys.argv[1:]]
N = R.NOW
CANDS = [("지금 규칙", N),
         ("warm 5", dict(N, warm_s=5)),
         ("lo 0.15", dict(N, lo=0.15)),
         ("lo 0.20", dict(N, lo=0.20)),
         ("warm 5 + lo 0.15", dict(N, warm_s=5, lo=0.15)),
         ("warm 5 + lo 0.20", dict(N, warm_s=5, lo=0.20)),
         ("conf 0.40 + warm 5 + lo 0.15", dict(N, conf_th=0.40, warm_s=5, lo=0.15)),
         ("conf 0.40 + warm 5 + lo 0.20", dict(N, conf_th=0.40, warm_s=5, lo=0.20)),
         ("conf 0.35 + warm 5 + lo 0.15", dict(N, conf_th=0.35, warm_s=5, lo=0.15)),
         ("conf 0.35 + warm 5 + lo 0.20", dict(N, conf_th=0.35, warm_s=5, lo=0.20))]

data = {}
for label, d in DUMPS:
    rows, poly, gt = R.load(d)
    if rows:
        data[label] = (rows, poly, gt, {s: R.zone_max_conf(rows[s], poly[s]) for s in rows})

print("%-30s" % "규칙(다른 값은 지금 값)" + "".join("  %-28s" % l for l in data))
for name, kw in CANDS:
    line = "%-30s" % name
    for label, (rows, poly, gt, zmax) in data.items():
        r = R.run(rows, poly, gt, zmax, lambda s, kw=kw: R.sa_entry(rows[s], poly[s], **kw))
        line += "  %6.2f (%2d/%d/%d) 여유 %.1f     " % (r["score"], r["tp"], r["fn"], r["fp"], r["edge"])
    print(line)
print("\n(점수 (맞음/놓침/오검), 여유 = 창 가장자리까지 최소 초. 지금 규칙 = conf %.2f corners %d hold %d gap %d)"
      % (N["conf_th"], N["corners"], N["hold"], N["gap"]))

# -*- coding: utf-8 -*-
"""문서에 같은 사실이 여러 곳에 적혀 있나. 숫자·고유명사를 기준으로 찾는다.
   같은 사실이 두 곳에 있으면 한쪽이 낡는다. 오늘 그것 때문에 여러 번 헤맸다."""
import collections
import re
from pathlib import Path

V = Path(__file__).resolve().parents[1]
DOCS = sorted(list((V / "docs").glob("*.md")) + list((V / "docs/kisa").glob("*.md")))

# 이 프로젝트에서 '사실' 을 이루는 조각들
PAT = {
    "점수": r"\b(?:100\.00|94\.74|96\.55|88\.89|82\.35|93\.10|84\.21|77\.78|90\.00|70\.59)\b",
    "클립": r"\bC00_\d{3}_\d{4}\b",
    "가중치": r"\b(?:fire_fog|fire_small|person_v[23]|fall_track|fire_snowfull)\.pt\b",
    "설정값": r"(?:smoke=1\.1|th 0\.755|gap=?2|conf 0\.45|불 0\.40|창 20|maxgap 20)",
    "데이터셋": r"\b(?:wildfire_pos|fasdd_snowfog|azimjaan|aihub71751|handset_fire_hn|handset_person)\w*\b",
}

where = collections.defaultdict(lambda: collections.defaultdict(int))
for f in DOCS:
    t = f.read_text(encoding="utf-8")
    for kind, pat in PAT.items():
        for m in re.findall(pat, t):
            where[(kind, m)][f.relative_to(V / "docs")] += 1

print("같은 사실이 세 곳 이상에 적힌 것 (한쪽이 낡을 자리)\n")
rows = [(k, d) for k, d in where.items() if len(d) >= 3]
rows.sort(key=lambda x: -len(x[1]))
for (kind, m), d in rows[:18]:
    files = " · ".join(f"{p}({n})" for p, n in sorted(d.items(), key=lambda x: -x[1]))
    print(f"  [{kind}] {m:<28} {len(d)}곳   {files}")

print()
print("문서별 총 사실 조각 수 (많을수록 남의 내용을 품고 있을 가능성)")
per = collections.Counter()
for (kind, m), d in where.items():
    for p, n in d.items():
        per[p] += n
for p, n in per.most_common():
    print(f"  {str(p):<34}{n:>5}")

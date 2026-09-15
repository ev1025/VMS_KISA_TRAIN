# -*- coding: utf-8 -*-
"""aihubshell 이 남긴 *.partN 조각을 오프셋 숫자 순서로 이어붙인다.

원본 aihubshell 은 한글 파일명에서 병합이 깨진다(printf %q 로 이스케이프한 이름을
find -name 에 넣어 매칭 0건 → 0바이트 파일 생성 → 조각까지 rm). 그래서 병합만 여기서 한다.
사용: python3 merge_parts.py <내려받은 폴더>
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
pat = re.compile(r"^(.*)\.part(\d+)$")

groups = {}
for p in root.rglob("*.part*"):
    m = pat.match(p.name)
    if m:
        groups.setdefault(p.parent / m.group(1), []).append((int(m.group(2)), p))

if not groups:
    print("병합할 조각 없음")
    sys.exit(0)

for out, parts in sorted(groups.items()):
    parts.sort()                                     # 오프셋 숫자순 (문자열 정렬이면 10GB 넘어가며 뒤섞인다)
    total = sum(p.stat().st_size for _, p in parts)
    with open(out, "wb") as w:
        for _off, p in parts:
            with open(p, "rb") as r:
                while True:
                    b = r.read(1 << 24)
                    if not b:
                        break
                    w.write(b)
    got = out.stat().st_size
    ok = got == total
    print(f"{'OK  ' if ok else '틀림'} {out.name}: 조각 {len(parts)}개 {total:,}B -> {got:,}B", flush=True)
    if ok:
        for _off, p in parts:
            p.unlink()                               # 병합 확인된 뒤에만 조각을 지운다

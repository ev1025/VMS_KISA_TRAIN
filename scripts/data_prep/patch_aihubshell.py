# -*- coding: utf-8 -*-
"""aihubshell 사본에서 병합·조각삭제 단계를 빼둔다(병합은 merge_parts.py 가 한다)."""
import io
import sys

p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()

old_cat = '''                        find "${target_dir}" -name "${escaped_prefix}.part*" -print0 | sort -zt'.' -k2V | xargs -0 cat > "${target_dir}/${prefix}" '''
old_rm = '''                        rm "${target_dir}/${prefix}".part*'''
assert s.count(old_cat) == 1, "병합 줄 못 찾음"
assert s.count(old_rm) == 1, "조각삭제 줄 못 찾음"

s = s.replace(old_cat, '                        : # 병합은 merge_parts.py 로 따로 한다(한글 파일명에서 원본 병합이 깨진다)')
s = s.replace(old_rm, '                        : # 조각 삭제도 하지 않는다')
io.open(p, "w", encoding="utf-8").write(s)
print("aihubshell 사본 패치 완료:", p)

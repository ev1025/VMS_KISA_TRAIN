# -*- coding: utf-8 -*-
"""학습 데이터 탭 메타: 사라진 dataset_24k → aihub71751_24k (images/·labels/ 가 train 하위 없이 바로 있는 구조도 읽게)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/build_dataset_meta.py"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new, 1)
rep('''    ("dataset_24k", "24k 방화 (AI허브 71751)", "data/학습데이터/dataset_24k", ["fire", "smoke"]),''',
    '''    ("aihub71751_24k", "24k 방화 (AI허브 71751)", "data/학습데이터/aihub71751_24k", ["fire", "smoke"]),''')
rep('''        di = G / rel / "images" / "train"
        if not di.is_dir():
            continue''',
    '''        di = G / rel / "images" / "train"
        if not di.is_dir():
            di = G / rel / "images"                     # train 하위 폴더 없이 images/ 에 바로 있는 세트
        if not di.is_dir():
            continue''')
rep('''        has_label = (G / rel / "labels" / "train" / (stem + ".txt")).exists()''',
    '''        has_label = (G / rel / "labels" / "train" / (stem + ".txt")).exists() or (G / rel / "labels" / (stem + ".txt")).exists()''')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")

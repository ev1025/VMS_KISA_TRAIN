# -*- coding: utf-8 -*-
"""'같은 사람에 박스 2개' 가 어디서 오나 센다. 덤프(모델 출력)와 학습 라벨 양쪽을 본다.

사용
    python scripts/dup_stats.py dumps <덤프폴더> [...]        # 표본당 박스 수 · 겹친 쌍(IoU>=0.3) · 포함된 쌍(작은 박스가 큰 박스 안 60%+)
    python scripts/dup_stats.py labels <labels/train 폴더> [...] [--limit N]
"""
import json
import random
import sys
from pathlib import Path


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def pair_kind(a, b):
    """겹침 종류: 'iou'(IoU>=0.3) · 'contain'(교집합이 작은 박스의 60%+) · None"""
    i = inter(a, b)
    if i <= 0:
        return None
    if i / (area(a) + area(b) - i) >= 0.3:
        return "iou"
    if i / max(1e-6, min(area(a), area(b))) >= 0.6:
        return "contain"
    return None


def dumps(folders, conf_th=0.40):
    print("%-44s %6s %7s %8s %8s %8s   %s" % ("덤프", "표본", "박스", "박스/표본", "IoU쌍", "포함쌍", "겹친 박스 비율(쌍/박스)"))
    for d in folders:
        frames = boxes = k_iou = k_con = 0
        for f in sorted(Path(d).glob("*.jsonl")):
            for line in f.read_text().splitlines():
                bs = [b[2:6] for b in json.loads(line)["boxes"] if b[1] >= conf_th]
                frames += 1; boxes += len(bs)
                for i in range(len(bs)):
                    for j in range(i + 1, len(bs)):
                        k = pair_kind(bs[i], bs[j])
                        k_iou += k == "iou"; k_con += k == "contain"
        print("%-44s %6d %7d %8.2f %8d %8d   %.1f%%" % (Path(d).name, frames, boxes, boxes / max(1, frames), k_iou, k_con,
                                                      100.0 * (k_iou + k_con) / max(1, boxes)))


def labels(folders, limit):
    print("%-40s %7s %7s %9s %8s %8s   %s" % ("라벨 폴더", "파일", "박스", "박스/파일", "IoU쌍", "포함쌍", "겹친 박스 비율"))
    for d in folders:
        files = sorted(Path(d).glob("*.txt"))
        if limit and len(files) > limit:
            files = random.Random(0).sample(files, limit)
        nf = boxes = k_iou = k_con = 0
        for f in files:
            bs = []
            for ln in f.read_text().splitlines():
                p = ln.split()
                if len(p) < 5:
                    continue
                cx, cy, w, h = map(float, p[1:5])
                bs.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
            nf += 1; boxes += len(bs)
            for i in range(len(bs)):
                for j in range(i + 1, len(bs)):
                    k = pair_kind(bs[i], bs[j])
                    k_iou += k == "iou"; k_con += k == "contain"
        print("%-40s %7d %7d %9.2f %8d %8d   %.1f%%" % (Path(d).parent.parent.name, nf, boxes, boxes / max(1, nf), k_iou, k_con,
                                                      100.0 * (k_iou + k_con) / max(1, boxes)))


if __name__ == "__main__":
    mode = sys.argv[1]
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    limit = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), "0"))
    (dumps(args) if mode == "dumps" else labels(args, limit))

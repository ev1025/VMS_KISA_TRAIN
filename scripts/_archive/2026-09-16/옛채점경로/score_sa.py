# -*- coding: utf-8 -*-
"""범용 SA 채점기: 예측 SA XML 폴더 vs GT(영상 옆 XML) → KISA 창규칙 F1.

sa_runner.py 가 뽑은 예측 XML(폴더)과 검증영상 옆 GT XML 을 대조한다.
규칙은 score_intrusion.py 와 동일:
  정검(TP): 예측 StartTime 이 [GT-2s, GT+10s] 안
  미검(FN): GT 있는데 예측 없음 또는 창 밖
  오검(FP): 예측 있는데 GT 없음 또는 창 밖  (창 밖은 오검+미검 동시)
출력 한 줄(결과 탭 파서 형식): "<태그> → <F1> (정검 X 미검 Y 오검 Z)"
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

BEFORE, AFTER = 2.0, 10.0


def hms(t):
    if not t:
        return None
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def start_of(xml_path):
    """XML 에서 첫 Alarm 의 StartTime(초). 없으면 None."""
    if not xml_path.exists():
        return None
    el = ET.parse(xml_path).getroot().find(".//Alarm/StartTime")
    return hms(el.text) if el is not None and el.text else None


def score(pred_dir, gt_dir, tag):
    tp = fn = fp = 0
    for mp4 in sorted(Path(gt_dir).glob("*.mp4")):
        stem = mp4.stem
        gt = start_of(mp4.with_suffix(".xml"))          # GT 는 영상 옆
        o = start_of(Path(pred_dir) / (stem + ".xml"))  # 예측은 pred 폴더
        if o is None:
            if gt is not None:
                fn += 1
        elif gt is not None and gt - BEFORE <= o <= gt + AFTER:
            tp += 1
        else:
            fp += 1
            if gt is not None:
                fn += 1
    r = tp / (tp + fn) if tp + fn else 0
    p = tp / (tp + fp) if tp + fp else 0
    f1 = 2 * r * p / (r + p) * 100 if r + p else 0
    return f1, tp, fn, fp


def demo():
    """규칙 자체 점검: 창 안/밖/미검/오검 각 1건 → 정검1 미검2 오검1."""
    import tempfile, os
    d = Path(tempfile.mkdtemp())
    (d / "gt").mkdir(); (d / "pred").mkdir()

    def w(folder, stem, sec, is_mp4=False):
        # 영상 옆 GT 는 mp4 도 있어야 glob 에 잡힘
        if is_mp4:
            (d / folder / (stem + ".mp4")).write_bytes(b"x")
        body = "<Alarm><StartTime>%s</StartTime></Alarm>" % (
            "%02d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)) if sec is not None else ""
        (d / folder / (stem + ".xml")).write_text(
            "<KisaLibraryIndex><Alarms>%s</Alarms></KisaLibraryIndex>" % body)

    w("gt", "a", 100, is_mp4=True); w("pred", "a", 105)   # 창 안 → 정검
    w("gt", "b", 100, is_mp4=True); w("pred", "b", 200)   # 창 밖 → 오검+미검
    w("gt", "c", 100, is_mp4=True); w("pred", "c", None)  # 예측 없음 → 미검
    w("gt", "d", None, is_mp4=True); w("pred", "d", 50)   # GT 없는데 예측 → 오검
    f1, tp, fn, fp = score(d / "pred", d / "gt", "demo")
    assert (tp, fn, fp) == (1, 2, 2), (tp, fn, fp)
    print("selftest OK:", (tp, fn, fp), "F1=%.2f" % f1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", help="예측 SA XML 폴더")
    ap.add_argument("--gt", help="GT(영상+xml) 폴더")
    ap.add_argument("--tag", default="기본")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        demo(); return
    f1, tp, fn, fp = score(a.pred, a.gt, a.tag)
    print("%s → %.2f (정검 %d 미검 %d 오검 %d)" % (a.tag, f1, tp, fn, fp))


if __name__ == "__main__":
    main()

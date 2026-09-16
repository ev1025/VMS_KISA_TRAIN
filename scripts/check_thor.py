# -*- coding: utf-8 -*-
"""Thor 배포본이 서버와 같은지 확인한다.

왜 있나 (2026-09-16)
    Thor 점수가 안 나오는 원인을 RTSP 손상으로 보고 있었는데, 실제로는 Thor 의
    kisa_items.py 가 09-15 15:55 판이라 그날 올린 규칙이 하나도 없었다.
    쓰러짐 th 0.269(구) 대 0.755(신), 방화 win 5 hits 3(구) 대 win 10 hits 3(신).
    서버 실측으로 쓰러짐 90.00->100.00, 방화 77.78->88.89 에 해당하는 차이다.

    사람이 눈으로 맞추면 또 어긋난다. 해시로 대조한다.

어디서 도나
    작업 PC 에서 돈다. 서버와 Thor 는 서로 못 붙는다(Thor 는 내부망, 서버는 원격).
    양쪽에 붙을 수 있는 것은 작업 PC 뿐이라 여기서 둘을 각각 물어 비교한다.

사용
    python scripts/check_thor.py
    되돌아온 값: 어긋난 파일이 있으면 1

    SRV_HOST  서버 ssh 이름 (기본 nhn-yolo)
    THOR_HOST Thor ssh 주소 (기본 mrod1@10.37.27.28)
    서버는 키 인증. Thor 는 키가 없으면 환경변수 MROD_PW 로 붙는다(비밀번호는 코드에 안 적는다).
"""
import os
import subprocess
import sys
from pathlib import Path

SRV = os.environ.get("SRV_HOST", "nhn-yolo")
SRV_ROOT = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
HOST = os.environ.get("THOR_HOST", "mrod1@10.37.27.28")
THOR = "/home/mrod1/Desktop/Project/Kisa"

# (서버 경로, Thor 경로) — 시험장에서 실제로 도는 것만 본다
PAIRS = [
    ("_kisa_port/tools/kisa_items.py",        f"{THOR}/tools/kisa_items.py"),
    ("_kisa_port/tools/rtsp_source.py",       f"{THOR}/tools/rtsp_source.py"),
    # 방화는 두 벌을 겹쳐 쓴다(2026-09-16). 한 벌만 낡아도 점수가 달라지므로 둘 다 본다.
    ("_kisa_port/weights/kisa/fire_fog.pt", f"{THOR}/weights/kisa/fire_fog.pt"),
    ("_kisa_port/weights/kisa/fire_small.pt", f"{THOR}/weights/kisa/fire_small.pt"),
    ("_kisa_port/weights/kisa/person_v2.pt",  f"{THOR}/weights/kisa/person_v2.pt"),
    ("_kisa_port/weights/kisa/person_v3.pt",  f"{THOR}/weights/kisa/person_v3.pt"),
    ("_kisa_port/weights/kisa/yolo11x-pose.pt", f"{THOR}/weights/kisa/yolo11x-pose.pt"),
    ("_kisa_port/weights/kisa/fall_track.pt", f"{THOR}/weights/kisa/fall_track.pt"),
]


def _parse(text):
    out = {}
    for ln in text.splitlines():
        h, _, p = ln.strip().partition("  ")
        if h and p:
            out[p.strip()] = h
    return out


def md5_on(host, paths):
    """그 장비에서 md5 를 받아 {경로: 해시} 로 돌려준다. 심링크는 따라간다.

    키 인증이 없으면 MROD_PW 비밀번호로 한 번 더 시도한다(Thor 가 그렇다).
    비밀번호는 코드에 적지 않는다. 환경변수로만 받는다.
    """
    line = "md5sum " + " ".join(f"'{p}'" for p in paths) + " 2>/dev/null"
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, line]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    out = _parse(r.stdout)
    if out:
        return out, r

    pw = os.environ.get("MROD_PW")
    if not pw:
        return out, r
    try:
        import paramiko
    except ImportError:
        return out, r
    user, _, addr = host.rpartition("@")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect(addr, username=user or None, password=pw, timeout=20)
        _, o, _e = c.exec_command(line, timeout=300)
        out = _parse(o.read().decode("utf-8", "replace"))
    except Exception as ex:                      # 붙지 못하면 원래 결과를 그대로 돌려준다
        r.stderr = (r.stderr or "") + " / 비밀번호 접속도 실패: " + repr(ex)
    finally:
        c.close()
    return out, r


def main():
    srv, rs = md5_on(SRV, [f"{SRV_ROOT}/{loc}" for loc, _ in PAIRS])
    if not srv:
        print(f"서버({SRV})에 붙지 못했습니다.")
        print("  " + (rs.stderr or "").strip()[-200:])
        return 2
    remote, r = md5_on(HOST, [t for _, t in PAIRS])
    if not remote:
        print(f"Thor({HOST})에 붙지 못했습니다.")
        print("  " + (r.stderr or "").strip()[-200:])
        print("  껐거나 주소가 바뀌었으면 THOR_HOST 로 지정하세요.")
        return 2

    bad = []
    print(f"서버 대 Thor({HOST})\n")
    for loc, rem in PAIRS:
        mine = srv.get(f"{SRV_ROOT}/{loc}")
        if mine is None:
            print(f"  [서버에 없음] {loc}"); bad.append(loc); continue
        theirs = remote.get(rem)
        if theirs is None:
            print(f"  [Thor 에 없음] {Path(rem).name}"); bad.append(loc); continue
        ok = mine == theirs
        print(f"  {'같음  ' if ok else '다름  '} {Path(loc).name:22s} {mine[:12]} {'=' if ok else '!='} {theirs[:12]}")
        if not ok:
            bad.append(loc)

    print()
    if bad:
        print(f"어긋난 것 {len(bad)}개. Thor 가 옛 규칙·가중치로 돌고 있다는 뜻이다.")
        print("  맞추는 법: 서버에서 해당 파일을 Thor 의 같은 자리로 복사한 뒤")
        print("  Thor 의 tools/__pycache__ 를 지운다(root 소유라 docker run 으로 지워야 한다).")
        return 1
    print("전부 같음. Thor 가 서버와 같은 규칙·가중치로 돈다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

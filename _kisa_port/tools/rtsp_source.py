# -*- coding: utf-8 -*-
"""RTSP 수신 소스 (시험장 경로).

원래 이 클래스는 VMS 앱의 app/vision/frame_sources.py 에 있고, kisa_items.py 는 거기서
임포트한다. 그런데 Thor 배포본에는 tools/kisa_items.py 한 파일만 올라가 있어서
--rtsp 로 실행하면 ModuleNotFoundError 로 즉사한다. 즉 오프라인 리허설은 되는데
정작 시험 당일 경로가 안 도는 상태였다. 그래서 앱 의존 없이 떼어 왔다.

원본에서 뺀 것 : go2rtc 소스, settings, requests. RTSP 수신에는 필요 없다.
원본에서 그대로 둔 것 : 아래 세 가지는 2026-09-09 VLC 2.1.5 드라이런에서 고친 것들이라
  손대면 안 된다.
    - TCP 먼저 시도하고 461 이면 UDP 로 폴백 (VLC 2.1.5 서버가 TCP 인터리브를 거부한다)
    - abs_pts : 서버 pts 가 클립 절대 재생위치다. 접속이 늦어도 시각이 안 밀린다
    - 프레임 받다 끊기면 세션 경계로 처리 (UDP 는 EOF 가 아니라 타임아웃으로 끝난다)
      여기서 안 넘기면 다음 클립이 이전 파일명으로 기록돼 이후 SA 가 전부 어긋난다
"""
import time
from typing import NamedTuple

PTS_BACK_MIN = 5.0    # 이만큼 뒤로 가야 경계 후보(초)
PTS_START_MAX = 5.0   # 그리고 클립 처음(0초) 근처여야 한다


class Frame(NamedTuple):
    session: str
    ts: float
    bgr: object
    jpg: object = None


class _SceneCut:

    def __init__(self, thresh):
        self.thresh = thresh
        self.prev = None

    def cut(self, bgr):
        if self.thresh is None:
            return False
        import cv2
        h = cv2.calcHist([cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)], [0], None, [64], [0, 256])
        cv2.normalize(h, h)
        prev, self.prev = self.prev, h
        if prev is None:
            return False
        return float(cv2.compareHist(prev, h, cv2.HISTCMP_CORREL)) < self.thresh


def _av_backend(url):
    """RTSP 는 TCP 를 먼저, 거부되면 UDP 로 (KISA 시험용 VLC 2.1.5 서버는 TCP 인터리브를 461 로 거부한다).
    timeout 2초 = 서버가 클립을 끝내고 다음 VLC 를 띄우는 공백을 빨리 '수신 중단' 으로 잡기 위함."""
    import av, os
    is_rtsp = str(url).lower().startswith("rtsp")
    order = [os.environ.get("KISA_RTSP_TRANSPORT", "tcp"), "udp"] if is_rtsp else [None]
    c = None; last = None
    for tr in dict.fromkeys(order):
        opts = {"rtsp_transport": tr, "timeout": "2000000"} if tr else {}
        try:
            c = av.open(url, options=opts)
            if tr:
                print(f"[RTSP] 연결 transport={tr}", flush=True)
            break
        except Exception as e:           # 461 Unsupported transport 등 → 다음 전송 방식
            last = e
    if c is None:
        raise last
    st = c.streams.video[0]
    fps = float(st.average_rate or 25)

    def gen():
        try:
            for f in c.decode(st):
                t = float(f.pts * st.time_base) if f.pts is not None else None
                yield f.to_ndarray(format="bgr24"), t
        finally:
            c.close()
    return gen(), fps


def _cv_backend(url):
    import cv2
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        cap.release()
        raise IOError(f"RTSP 열기 실패: {url}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    def gen():
        try:
            while True:
                ok, f = cap.read()
                if not ok:
                    return
                yield f, None
        finally:
            cap.release()
    return gen(), fps


def default_backend(url):
    try:
        import av  # noqa: F401
    except ImportError:
        return _cv_backend(url)
    return _av_backend(url)


class RtspSource:
    realtime = False
    record = False

    def __init__(self, url, names=None, stride_s=0.5, scene_thresh=None,
                 retry_s=1.0, max_retry=5, min_session_s=3.0, backend=None, abs_pts=False):
        # abs_pts: 서버의 pts 가 클립 재생위치(절대시각)일 때 True. KISA VLC 서버가 그렇다(늦게 붙어도 pts=경과시각).
        #          False 면 첫 pts 를 0 으로 놓는다(일반 카메라). 절대 pts 면 접속이 늦어도 시각이 안 밀리고,
        #          다음 클립은 pts 가 작아지므로 'PTS 역전' 으로 경계가 확실히 잡힌다.
        self.abs_pts = abs_pts
        self.url = url
        self.names = list(names or [])
        self.stride_s = stride_s
        self.retry_s = retry_s
        self.max_retry = max_retry
        self.min_session_s = min_session_s
        self.backend = backend or default_backend
        self.name = "rtsp"
        self.cuts = []
        self._scene_thresh = scene_thresh
        self._it = None
        self._fps = 25.0
        self._idx = 0
        self._fails = 0
        self._empty = 0
        self._n = 0
        self._last_t = None
        self._t0 = None
        self._scene = _SceneCut(scene_thresh)

    @property
    def session(self):
        if self.names:
            return self.names[self._idx] if self._idx < len(self.names) else None
        return f"clip{self._idx + 1}"

    def _advance(self, why, force=False):
        if not force and self._n / max(self._fps, 1.0) < self.min_session_s:
            return False
        self.cuts.append({"session": self.session, "why": why,
                          "at_s": round(self._n / max(self._fps, 1.0), 2)})
        print(f"[RTSP] 세션 경계: {self.session} ← {why}", flush=True)
        self._idx += 1
        self._n = 0
        self._t0 = None
        self._last_t = None
        self._scene = _SceneCut(self._scene_thresh)
        return True

    def read(self):
        while True:
            if self.session is None:
                return None
            if self._it is None:
                try:
                    self._it, self._fps = self.backend(self.url)
                    self._fails = 0
                except Exception as e:
                    self._fails += 1
                    if self._fails > self.max_retry:
                        print(f"[RTSP] 재연결 포기 ({self._fails}회): {e}", flush=True)
                        return None
                    time.sleep(self.retry_s)
                    continue
            try:
                bgr, t = next(self._it)
            except StopIteration:
                self._it = None
                if self._n == 0:
                    self._empty += 1
                    if self._empty > self.max_retry:
                        print(f"[RTSP] 빈 스트림 {self._empty}회, 종료", flush=True)
                        return None
                else:
                    self._empty = 0
                self._advance("EOF", force=True)
                continue
            except Exception as e:
                self._it = None
                self._fails += 1
                if self._n > 0:
                    # 프레임을 받다가 끊김 = 서버가 그 클립을 끝냈다(UDP 는 EOF 가 아니라 타임아웃으로 온다).
                    # 여기서 세션을 넘기지 않으면 다음 클립 프레임이 이전 파일명으로 기록돼 이후 SA 가 전부 어긋난다.
                    self._advance("수신 중단(스트림 끊김)", force=True)
                if self._fails > self.max_retry:
                    print(f"[RTSP] 수신 중단 ({e})", flush=True)
                    return None
                continue

            if t is not None:
                # 새 클립 = 크게 뒤로 갔고(PTS_BACK_MIN) 동시에 클립 처음으로
                # 돌아왔을 때(PTS_START_MAX)만. 둘 중 하나만으로는 UDP 지터와 구분이 안 된다.
                if (self._last_t is not None
                        and t + PTS_BACK_MIN < self._last_t
                        and t < PTS_START_MAX):
                    self._advance("PTS 역전")
                    self._last_t = t
                else:
                    # 기준은 지금까지의 최대치. 지터 프레임 하나에 기준이 끌려가지 않게.
                    self._last_t = t if self._last_t is None else max(self._last_t, t)
                if self._t0 is None:
                    self._t0 = 0.0 if self.abs_pts else t

            self._n += 1
            step = max(1, int(round(self._fps * self.stride_s)))
            if (self._n - 1) % step:
                continue

            if self._scene.cut(bgr):
                self._advance("장면 급변")

            ts = (t - self._t0) if (t is not None and self._t0 is not None) \
                else (self._n - 1) / max(self._fps, 1.0)
            return Frame(self.session, max(0.0, ts), bgr)

    def close(self):
        self._it = None

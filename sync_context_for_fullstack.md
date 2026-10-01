# ML → 대시보드 인수인계 (sync_context_for_fullstack.md)

기준일 2026-10-01 · 계약 버전 v2(ml_changelog.md 참고) · 이 문서는 ML 세션이 관리한다

- 읽는 사람: 대시보드(풀스택) 세션. 이 문서가 첫 입력이다
- 고치는 사람: ML 세션만. 틀린 곳 · 빠진 곳은 `ml_changelog.md` 맨 아래 '풀스택 → ML 요청' 절에 적는다
- 표기: `vms/` = 저장소 루트. 경로는 전부 저장소 상대경로. 약어는 첫 등장에서 괄호로 푼다

---

## 0. 읽는 순서

| 순서 | 읽을 것 | 왜 |
|---|---|---|
| 1 | 이 문서(특히 1 · 2 · 4 · 7 · 10 · 12절) | 경계 · 계약 · 금지 · 첫 할 일 |
| 2 | `ml_changelog.md` 머리의 `미확인:` 항목(v1 · v2) | 아직 화면에 반영 안 된 계약 변경 |
| 3 | `docs/dashboard.md` | 지금 대시보드 설명(풀스택 소유 문서) |
| 4 | `dash_v2/serve_kisa.py` · `dash_v2/results_newdata.py` · `dash_v2/dashboard.html` · `dash_v2/js/*.js` | 고칠 코드 |
| 5 | `configs/result_blocks.yaml` · `configs/history.yaml`(둘 다 읽기만) | 화면에 실리는 데이터의 실물 |
| 6 | `docs/file_path.md` · `CLAUDE.md` | 배치 규칙 · 커밋 전 점검 |
| 7 | `results/<판>/meta.json` 두어 개 · `dumps/review/<판>/<ckpt>/<item>/summary.json` 한 개 | 스키마 실물 확인 |

---

## 1. 한눈에

### 1-1. 무엇이 어디에

| 것 | 내용 |
|---|---|
| 저장소 | `vms/` 하나. ML 파이프라인(`scripts/` · `model.py` · `score_kisa.py`)과 대시보드(`dash_v2/`)가 같이 있음. 심링크 · 중복 폴더 금지 |
| DB(데이터베이스) | 없음. 전부 YAML(YAML Ain't Markup Language, 설정 파일 형식) · JSON(JavaScript Object Notation, 자료 교환 형식) · txt · mp4 |
| 서버 A | 학습 서버. 저장소 원본(git). GPU(Graphics Processing Unit, 그래픽 처리 장치) 학습 · 큐 러너(tmux). 대시보드 A 는 히스토리 읽기 전용 |
| 서버 B | 사본 서버(git 아님). 히스토리 원본(환경변수 `VMS_HISTORY_EDIT=1`). `dash.sh start / stop / status` 로 대시보드 기동 · 정지. `runs/` 는 새 데이터 판 13개만, `_exp/` · `logs/queue/` 없음(큐 상자 비어 있음), `results/` 는 `run_info.json` 으로 읽음 |
| 작업 PC(채점 전용 PC) | 사람 · 방화 판의 공식 채점(`score.txt` · `score_pc.txt`)과 검수 캐시(`dumps/review/`)를 저장소 밖 스크립트(`pc_review.py` · `eval_watch*`)로 만들어 서버에 넣음. 대시보드 코드와 무관 |
| 시험 PC | KISA(한국인터넷진흥원) 인증 시험용 판정기(별도 저장소 VMS_KISA). 이 저장소의 대시보드와 무관 |
| 대시보드 | `dash_v2/serve_kisa.py`(파이썬 표준 ThreadingHTTPServer, 프레임워크 없음). 포트 8890 고정, 루프백에만 바인드 → ssh(Secure Shell, 원격 접속) 터널로 본다. 같은 프로세스가 SAM2(Segment Anything Model 2, 분할 모델) 모델과 전파 워커를 품는다 |
| 탭 | 데이터 확인 · 영상 검수 · 결과 · 히스토리(4개). `/api/pushinfo.enabled` 가 참이면(작업대 모드) 데이터 확인만 |
| 결과 데이터 | git 에 없음(`results/*` · `dumps/*` · `logs/*` · `data/*`). 서버 A → B 는 ML 이 직접 복사 |

### 1-2. 세션 경계(dash_v2 확장. 새 앱 · 새 스택 금지)

| 경로 | ML 세션 | 풀스택 세션 |
|---|---|---|
| `scripts/`, `model.py`, `score_kisa.py`, `_kisa_port/`, `configs/queue_*.yaml`, `configs/result_blocks.yaml`, `configs/datasets.yaml`(손 편집), `results/`, `runs/`, `dumps/`, `data/`, `logs/`, `_exp/`, `docs/`(dashboard.md 제외), `CLAUDE.md`, `README.md`, `sync_context_for_fullstack.md` | 쓰기 | 읽기만 |
| `dash_v2/**`, `docs/dashboard.md` | 읽기만. 고칠 것은 `ml_changelog.md` '풀스택 → ML 요청' 절 | 쓰기 |
| `configs/history.yaml` | B `/api/history` 로만(daily-report 스킬). B → A 복사 · 커밋은 ML | B 대시보드 화면으로만. 손 편집 · 커밋 금지 |
| `ml_changelog.md` | 항목 추가 | `확인:` 줄 + 요청 절 |

### 1-3. git · 프로세스 규칙

- `git add <자기 경로>` 만. `git add -A` · `git commit -a` 금지
- 커밋 제목 접두어: ML `[ml]`, 풀스택 `[dash]`. 푸시 전 `git pull --rebase`
- 커밋 전 `scripts/check_layout.py --all`(풀스택은 `dash_v2/` 에 `*.log` 없음만 해당)
- 대시보드 프로세스 재시작은 풀스택만, SAM2 전파 작업이 없을 때만. tmux 러너 · `scripts/exp_queue.py` 는 ML 만
- B 배포: 풀스택이 `dash_v2/*.py` · `dash_v2/js/*.js` · `dash_v2/dashboard.html` 복사(`dash_v2/js/host.js` 제외, 서버마다 다른 이름표). `results/` · `dumps/review/` 복사는 ML
- 검수 · 점수 파일은 KISA 파생(구역 다각형 · 정답 시각 포함) → 어떤 형태로도 커밋 금지

---

## 2. 항목 이름 표

계층마다 이름이 다르다. 전역 필터는 아래 3줄로 묶는다(계약 v2).

| UI | `meta.item` | kisa `--item` = `dumps/review` 폴더 | 검수 API `item=` | `dash_meta` 키 | SA(경보 결과 XML, 인증 안내서 용어) `AlarmDescription` | history `item` |
|---|---|---|---|---|---|---|
| 화재 | 방화 | fire | fire | fire | FireDetection | 방화 |
| 배회·침입 | 사람(옛 판: 침입 · 배회) | intrusion · loitering | intrusion · loiter | intrusion · loiter | Intrusion · Loitering | 사람 |
| 쓰러짐 | 쓰러짐 | falldown | fall | fall | Falldown | 쓰러짐 |

- `meta.item = "사람"` 은 사람 검출 모델 판. 침입 · 배회를 둘 다 채점한다. `results_newdata.ITEMS = {"사람": ["intrusion","loitering"], "방화": ["fire"]}`
- `result_blocks.yaml` 키: `dv` · `rule` 은 사람 / 방화, `judge` 는 침입 / 배회 / 방화 / 쓰러짐
- 시험 PC 결과 폴더 · `BASELINE.json` 항목은 한글(방화 · 침입 · 배회 · 쓰러짐)
- 함정: 검수 API 와 `dash_meta` 는 `loiter` · `fall`, 덤프 폴더와 kisa 항목명은 `loitering` · `falldown`
- 영상 폴더(`scripts/kisa_paths.py ITEM_DIR`, 괄호 숫자는 원본 그대로): 방화 `방화(10개)/배포` · 침입 `침입(30개)/배포` · 배회 `배회(30개)/배포` · 쓰러짐 `쓰러짐(10개)/배포`

---

## 3. 학습 파이프라인

### 3-1. 한 줄 흐름

원본 영상(`data/원본데이터/`) → 라벨(손라벨 · SAM2 전파 · 정답라벨 복사본, `data/학습데이터/{손라벨,자동라벨,정답라벨}/`) → 학습셋(`scripts/build_trainset.py` → `data/학습데이터/trainset_*`) → 큐 yaml(`configs/queue_*.yaml`) → 러너(`scripts/exp_queue.py`, tmux) → 학습(`model.py`, YOLO(You Only Look Once, 객체 검출 모델) → `runs/<판>/`) → mAP(mean Average Precision, 검출 정확도 지표) 측정(`scripts/eval_map.py`) → 채점(서버 방화 `score_kisa.py --tiles`, 공식 점수는 작업 PC) → 검수 캐시(`dumps/review/`, 작업 PC) → 비교 블록(`configs/result_blocks.yaml`, ML 손 편집) → 대시보드 결과 · 검수 탭.

### 3-2. 고정 산출 위치 · 명명

| 산출물 | 위치 |
|---|---|
| 가중치 | `runs/<판>/<모델>/weights/{best,last,epoch0,epoch10,…}.pt` (`save_period=10`) |
| 학습 설정 · 곡선 | `runs/<판>/<모델>/{args.yaml, results.csv}` |
| 점수 · 설정 | `results/<판>/{score.txt, meta.json, eval_map.json, run_info.json}` |
| 학습 로그 | `logs/queue/<판>.log`, 러너 `logs/queue/runner.log` |
| 목록 · 캐시 | `_exp/<판>/`(러너가 만들고 채점 뒤 지움) |
| 검수 캐시 | `dumps/review/<판>/<ckpt>/<item>/` |
| 규칙 평가 | `dumps/ruleeval/rule3.json`, `dumps/ruleeval/b_eval_20260930/` |

- 학습셋 이름 `<항목>_<comp|mask>[_hn]_<날짜>`, 판 이름 `<f|p><해상도>_<comp|mask>[_hn]_x<배율>_<날짜>`(f = 방화, p = 사람). `hand` · `_s` 안 씀
- 평가 해상도 = 학습 해상도. 학습은 한 번에 하나(`--jobs 1`). 손라벨은 같은 스냅샷끼리만 비교
- 에폭 번호: ultralytics 8.4.138 은 0부터 세어 `epoch10.pt` = 11번째 에폭 끝 = `results.csv` 의 `epoch=11` 행
- ckpt(checkpoint, 학습 중 저장한 가중치) `best` 기준 = 설치판은 mAP50-95 만(`fitness: map50` 옵션은 09-30 기각)

### 3-3. 단계(그리드) 0 ~ 4

코드 → 이름표는 `configs/result_blocks.yaml` 의 `phases`(4-6절). 화면은 이름표를 그대로 쓴다.

| 코드 | 이름표 | 담는 것 | 상태(10-01) | 결과 위치 |
|---|---|---|---|---|
| grid0 | 0단계(옛 방화 판 앙상블 기준값, 학습 없음) | 옛 방화 판 두 벌 조합의 기준값. 학습 없음 | 끝(기준값만) | 결과 탭 방화 판정기 설정(`judge.방화.tried`) · 히스토리. 판 폴더 없음 |
| grid1 | 1단계(해상도 × 배치 비교) | 사람(배경 10% 셋) 1280 b85 · b170, 960 b160 · b320, 640 b360 · b720. 방화 960 b160(배경 28% 시험 판으로 대신) · b320, 640 b360 · b720 | 학습 전부 끝(10-01 13:26). 사람 960 b320 공식 채점 중. 승자 = 사람 1280 배치 85 · 방화 960 배치 160(판정 기록은 히스토리) | `configs/queue_grid1a~d_*.yaml` · `results/<판>/meta.json`(`phase: grid1` 소급) · `result_blocks.yaml` 의 1단계 블록(`blocks[].id`, 부속 블록도 큐 이름 규칙대로 `grid1`). 판 이름 예 `p1280_grid_b85_bg10_20260928` · `p960_grid_b160_bg10_20260929` · `p640_grid_b360_bg10_20260929` · `f640_grid_b360_20260930` · `f960_bgtest_bg28_b160_20260928` |
| grid2 | 2단계(승자 설정에서 한 요인씩: 데이터 · 합성 · 학습 설정 · 모델 크기) | 1단계 승자 설정에서 한 요인씩: 데이터(① 군중 제거 · ② 작은 사람 제거 · ③ 둘 다) · 합성 · 학습 설정 · 모델 크기(11n · 11m) · 지식증류 KD(Knowledge Distillation, 큰 모델이 작은 모델을 가르침) | 진행. 10-01 14:06 사람 데이터 요인 6판 시작(`configs/queue_grid2a_20261001.yaml`, 블록 `grid2_person_bg_hn` · `grid2_person_crowd_tiny`). 방화 · 모델 크기는 그 뒤 | 히스토리 항목(할 일 + `cond`). 판이 생기면 블록 `grid2_*` |
| grid3 | 3단계(규칙 고르기: 안 본 편에서 G · B · T, 채점편은 측정만) | 규칙 벌 G · B · T(+S)를 학습에 안 쓴 영상(침입 117 · 배회 91 · 방화 헛불 38편)에서 고름. 채점편은 측정만 | 1단계 판 분량은 끝(09-30 서버 B 밤 평가). 남은 1단계 판 · 2단계 판은 아직 | `dumps/ruleeval/rule3.json`(결과 탭 '3규칙 F1') · `dumps/ruleeval/b_eval_20260930/` · `result_blocks.yaml judge.tried[]`(`phase` 칸) |
| grid4 | 4단계(결선: 상위 판 재확인 · 판정기 기술 · 앙상블 · 속도) | 상위 판 재확인 · 판정기 후처리 기술(조각 정리 등) · 방화 두 벌 앙상블 · 속도 관문 | 대기 | 히스토리 항목(할 일, `cond: 그리드 4단계`) |

### 3-4. 쓰러짐은 그리드 밖

- 모델: `yolo11x-pose` 자세 추정 + 시퀀스 분류기 3벌(로짓 평균). 0.5초 슬롯 · 20슬롯(10초) 창 · 59차원 피처 · 문턱 0.80 · 5창 연속
- 시험셋: 학습에 안 쓴 AI허브 쓰러짐 35편(일반화 잣대) + 연구개발 330편 교차검증. 채점 10편은 측정만
- 결과: 서버 B `kisa_eval/fall_diag` · `runs/fall_vanish`, 서버 A `dumps/fall_seq_*`(5-5절)
- 대시보드: 점수 카드 = `result_blocks.fall_ref` 고정, 검수 = `falldown_deploy|배포`(해상도 1280) 고정. `meta.json` 도 `phase` 도 없음. 히스토리 `item: 쓰러짐`

---

## 4. 실험 메타 계약

### 4-1. `results/<판>/meta.json` (쓰는 곳 `scripts/exp_queue.py write_meta()`)

| 키 | 타입 | 뜻 |
|---|---|---|
| `name` | str | 판 이름 = 폴더 이름 |
| `item` | str | `방화` · `사람` · `침입` · `배회` · `쓰러짐`. 큐 항목의 item, 없으면 방화 |
| `model` | str | 시작 가중치 이름(`yolo11s` = COCO(Common Objects in Context, 공개 데이터셋) 사전학습). `yolo` 로 시작하지 않으면 이어 학습 판 |
| `base` | str | 베이스 학습셋 이름(`data/학습데이터/<이름>`) |
| `extras` | list[str] | 더한 학습셋 |
| `oversample` | {셋: int} | 반복 배율(목록에 경로를 반복해 넣음) |
| `train` | dict | `epochs`, `batch`, `imgsz`, `multi_scale`, `cache`, `workers`, 선택적으로 `fitness`(`map50`), `lr0` |
| `extra` | dict | ultralytics 인자 그대로(`patience`, `seed`, `scale` 등) |
| `base_frac` | float | 베이스 표본 비율 |
| `n_train` | int 또는 null | train.txt 줄 수(첫 줄 더미 제외) |
| `best_pt` | str 또는 null | 학습 서버 절대경로. 사본 서버는 `review_cache.local_path()` 가 `runs/…` 로 바꿔 읽음 |
| `source` | dict | `{요구_긴변, 사본_사용: {r960\|r1280: n}, 원본_사용: n, 판정}` |
| `started`, `ended` | str | `YYYY-MM-DD HH:MM:SS` KST(한국 표준시) |
| `status` | str | 아래 표 |
| `phase` | str 또는 null | **계약 v1(새).** `phases` 코드(`grid0` ~ `grid4`). 없음 · null = 그리드 밖 |

`status` 값:

| 값 | 뜻 |
|---|---|
| `trained` | 학습 끝. 채점은 떼어 돌리거나 작업 PC 가 함 |
| `done` | 서버 채점까지 끝 |
| `train_failed` | 학습 실패 |
| `error: <repr>` | 예외 |

- 옛 판에만 있는 키: `note`, `출처`, `기법`, `손라벨`, `run` · `pc` · `ingested_at`(exam_pc) 등. 화면은 무시
- `role`(대조군 · 실험군) 키는 없고 앞으로도 안 만든다. 역할은 블록 `control` 로만 정해진다. 한 판이 블록마다 다른 역할일 수 있다
- 표식 파일 `results/<판>/SCORE_ON_THOR`(사유 한 줄): 있으면 서버 채점을 건너뜀(작업 PC 가 채점)

### 4-2. `phase` 가 들어가는 곳(계약 v1)

| 어디 | 값 | 누가 |
|---|---|---|
| `configs/result_blocks.yaml` 최상위 `phases` | 코드 → 이름표 사전(4-6절) | ML |
| 큐 yaml 실험 항목 `phase: grid2` | 새 큐부터. 돌고 있는 큐 yaml 은 편집 안 함 | ML |
| `results/<판>/meta.json` `phase` | 러너가 큐 항목에서 복사. 1단계 끝난 판은 `grid1` 소급(1회성) | ML |
| `result_blocks.yaml judge.tried[].phase` | 규칙 벌 `grid3` · 판정기 기술 `grid4` · 체크포인트 고르기 `grid1` · 옛 앙상블 `grid0` | ML |
| `/api/result_blocks` 응답 `runs[판].phase` | `meta.phase` 1줄 전달 | 풀스택(12절 3번) |
| `configs/history.yaml` 항목 `phase` | 7절 | ML(API) · 사용자(화면) |

주의: 이름이 같고 뜻이 다른 `phase` 가 둘 있다. `/api/queue jobs[].phase` = 학습 파이프라인 상태(`학습 중` · `mAP 검증 중` · `KISA 채점 중` · `끝`), `dumps/ruleeval/b_eval_*` 덤프의 `phase` = 시작 프레임 오프셋. 단계 코드와 섞지 말 것.

### 4-3. `results/<판>/run_info.json` (쓰는 곳 `dash_v2/results_newdata.run()`)

쓰는 조건 다섯 가지 모두: `meta.status == "trained"` · 실제 `args.yaml` 있음 · `results.csv` 있음 · 검증셋 key 를 앎 · 파일이 아직 없음. 학습 서버에서 GET `/api/result_blocks` 때 한 번 쓰고, 사본 서버(B)는 이 파일로 읽는다.

| 키 | 타입 | 뜻 |
|---|---|---|
| `args` | dict | `args.yaml` 에서 `SKIP`(name, project, data, save_dir, exist_ok, resume, workers, cache, device, plots, verbose, save, save_period, time)을 뺀 것. `model` 은 파일 이름만. `optimizer` 는 러너 로그의 실제 값. `fitness` 는 meta 또는 큐에서, 기본 `map5095` |
| `val` | dict | `{key: 목록 해시 10자 \| "val_small" \| null, text: "자체 CCTV 552장" 등, note: "미학습 클립" \| "학습과 겹침" \| "미정"}` |
| `epochs_run` | int | `results.csv` 데이터 줄 수 |

### 4-4. `score.txt` 다섯 형식과 파서(`scripts/review_cache.official()`)

**(1) 작업 PC 형식**(사람 새 판. 검수 · 결과 탭이 읽는 형식)
```
=== <실험> (작업 PC 채점 · MM-DD HH:MM) ===
--- best ---
intrusion 1280 (작업 PC): 정검 26 미검 4 오검 0 → 점수 92.86 (30편)
  틀린 편: C00_014_0002 ? 미검(gt=197 sa=None) | C00_275_0001 ? 오검(gt=134 sa=33.5)
loitering 1280 (작업 PC): ...
  틀린 편: ...
--- last ---
...
```
- `틀린 편` 에는 틀린 편만. 나머지는 정검. `?` 는 파일에 실제로 있는 글자
- 정규식: `RE_SEC ^--- (best|last|epoch\d+) ---` · `RE_ITEM ^(intrusion|loitering|fire) (\d+) \(작업 PC\): 정검 … → 점수 …` · `RE_BAD (C00_\d+_\d+) \? (미검|오검)\(gt=… sa=…\)`. `epochN` 절은 버림

**(2) 작업 PC 방화 `score_pc.txt`**
```
=== <실험> (작업 PC 채점 · MM-DD HH:MM) ===
--- epoch10 ---        (epoch20 … epoch50, best, last)
fire 960 한 벌 (작업 PC): [fire] 정검 6 미검 4 오검 4 → 점수 60.00 (90 미달)
클립 C00_012_0007: 정검 (gt=224 sa=224.5)          ← 10편 모두 한 줄씩
```
- 정규식: `RE_FIRE`, `RE_CLIP ^클립 (C00_\d+_\d+): (미검|오검)`

**(3) 서버 방화**(`exp_queue.score` → `score_kisa.py --tiles`)
```
=== <실험> 타일 ===
  덤프 <클립> × 10
=== <실험> (tiles=True) ===
  <규칙 이름>          →  73.68  (정검 7 미검 3 오검 2)     ← 규칙마다 한 줄. '배포 …' 가 실제 배포 규칙
=== 클립별 (<규칙>) ===
  클립 C00_089_0001: 미검+오검1 (gt=218 sa=[231.5])
```
- 신규칙 절에는 `신규칙 …`, `신클립 …` 줄이 붙음

**(4) 서버 사람 옛 형식**(09-27 이전)
```
=== <실험> 사람 항목 ===
침입 학습해상도 1280: [intrusion] 정검 24 미검 6 오검 0 → 점수 88.89 (90 미달)
침입 배포해상도 960: [intrusion] … 합격
```

**(5) 시험 PC 수집**(`scripts/exam_ingest.py`): 줄마다 `fire → 90.00 (정검 9 미검 1 오검 1)`, 아래에 기준값과 다른 편

- 기타: `(항목 X 채점기 미연결)` 줄만 있는 파일이 있음
- `score.txt` 가 있으면 러너는 끝난 판으로 보고 건너뜀. 화면이 이 파일을 쓰는 일은 없음

### 4-5. `results/` 루트 파일(화면 참고용)

| 파일 | 내용 | 관리 |
|---|---|---|
| `MODELS.json` | 가중치 계보 `{models: {파일.pt: {sha256_16, path, size_mb, task, used_by, kisa_f1, base_model, train, dataset, note, …}}, retired, alternatives}` | 사람 · `check_models.py` |
| `BASELINE.json` | 4항목 실측 `항목.<방화\|침입\|배회\|쓰러짐>: {점수, 정검, 미검, 오검, 로그, 측정일, 구성, …}`, `오프라인_재현_상태` | 실측만 기록 |
| `SUMMARY.md` | `build_summary.py` 표. 사람 판 점수가 전부 `-`(11절 1번) | 자동 |
| `loocv_results.json` | 09-07 판 그대로 | 낡음 |

`results/` 바로 아래 임의 `<이름>.txt` 금지(옛 `/api/results` 가 읽어 버림).

### 4-6. `configs/result_blocks.yaml` 스키마(사람이 정하는 값만) + `phases`

| 키 | 형식 | 뜻 |
|---|---|---|
| `phases` | `{grid0..grid4: 이름표}` | **계약 v1(새).** 코드 → 화면 이름표. 아래 블록 그대로 |
| `dv` | `{사람\|방화: [str]}` | 종속변수 문구 |
| `rule` | `{사람\|방화: [str]}` | 판정 기준 문구 |
| `key_clips` | `{방화: [클립 4개]}` | 변별 편 |
| `terms` | `[{g: 묶음, t: 용어, d: 설명}]` | 맨 위 '용어 정리'. ML 이 `n · m`(모델 크기) · `kdm`(증류 학생) 추가 |
| `fall_ref` | `{f1, tp, fn, fp, model}` | 쓰러짐 점수 카드 · 검수 기준값 |
| `judge` | `{침입\|배회\|방화\|쓰러짐: {applied: [str], tried: [{name, what, dec, result, why, variant?, phase?}]}}` | 점수 카드를 누르면 나오는 판정기 설정. `dec` ∈ 채택 · 기각 · 보류 · 확인 중. `variant` = review_post 기술 id. `phase` = 규칙 벌 항목 `grid3` · 판정기 기술 `grid4` · 체크포인트 고르기 `grid1` · 옛 앙상블 `grid0` |
| `blocks` | 목록(현재 10개) | 비교 블록 |

```yaml
phases:   # 그리드 단계(09-28 계획). 값 = 화면 이름표. 코드는 meta.json · 큐 yaml · history 의 phase 에 씀. 없음 = 그리드 밖
  grid0: "0단계(옛 방화 판 앙상블 기준값, 학습 없음)"
  grid1: "1단계(해상도 × 배치 비교)"
  grid2: "2단계(승자 설정에서 한 요인씩: 데이터 · 합성 · 학습 설정 · 모델 크기)"
  grid3: "3단계(규칙 고르기: 안 본 편에서 G · B · T, 채점편은 측정만)"
  grid4: "4단계(결선: 상위 판 재확인 · 판정기 기술 · 앙상블 · 속도)"
```

`blocks` 원소:

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 필수 | 블록 id |
| `phase` | 선택 | **계약 v1(새).** 블록의 단계 코드. 없으면 대조군 판의 `meta.phase`. 2단계 블록은 대조군이 1단계 판이라 블록에 적혀 있다. 응답으로 넘기려면 `results_newdata.block()` 키 튜플에 `phase` 추가(풀스택 1줄) |
| `date` | 필수 | `MM-DD` |
| `title`, `question` | 필수 | 제목('A vs B' 로 읽히게), 목적 |
| `iv` | 필수 | 독립변수(목록) |
| `vary` | 필수 | 판마다 달라도 되는 설정 키. `data`, `val`, 또는 args 이름(`imgsz`, `batch`, `epochs`, `seed`, `fitness` 등) |
| `control` | 필수 | 대조군 판 이름 |
| `runs` | 필수 | `{판: 조건 문구}`. 대조군 포함 |
| `same_data` | 필수 | 통제 데이터 문구 |
| `rule_extra`, `conclusion`, `note` | 선택 | 목록 |

- 블록 = 대조군 하나 + `runs`. 화면은 `control` 외를 실험군으로 본다
- 블록에 없는 새 데이터 판은 `others` 로. 대상 = `review_cache.eligible()` 판 + `runs/*/*/results.csv` 가 있고 results 기록이 없는 현역 판(모델이 `yolo` 로 시작하고 '지금 데이터')
- 검수 탭 그룹도 같은 블록을 쓴다

### 4-7. GET `/api/result_blocks` 응답

최상위: `{dv, rule, key_clips, terms, phases, blocks: [block], others: [판], runs: {판: run}, score: [카드], rule3: {made, rate, picks}}`. 결과가 없으면 `{error}`.
- `phases` 는 YAML 최상위 키가 그대로 실리는 전제(ML 확인). 응답에 없으면 요청 절에 적을 것

block 응답:

| 키 | 뜻 |
|---|---|
| `id`, `date`, `title`, `question`, `iv`, `rule_extra`, `same_data`, `conclusion`, `note` | YAML 그대로 |
| `control`, `members` | 대조군, 나머지 판 |
| `labels` | `= runs`(조건 문구) |
| `item` | `사람` 또는 `방화` |
| `same` | `{train: [[키, 값]], rest: int, data: [공통 셋], data_all: bool, val: {key, text, note} 또는 null}` |
| `diffs` | `[{key, values: {판: 값}, label, declared(= vary 안), harmless?}]`. declared 가 거짓이면 화면에 '교란 변수' |
| `planned` | 계획값만 있는 판이 있는가 |
| `verdicts` | `{판: {delta: {item: 정검차}, total, call: 동률\|개선\|하락} 또는 null}` |

run 응답:

| 키 | 뜻 |
|---|---|
| `exp`, `item`, `items` | 판, 사람/방화, 채점 항목 목록 |
| `status` | `done`, `scoring`, `train`, `queue`, `skip`, 또는 meta.status 원값 |
| `new` | '지금 데이터' 판인가 |
| `data` | 이름 목록, 오버샘플은 `"<셋> ×k"` |
| `n_train`, `args`, `planned`, `epochs_run`, `val`, `ended` | 4-1 · 4-3 참고 |
| `scores` | `{item: {best\|last: {tp, fn, fp, f1, res, bad: {클립: 미검\|오검}}}}` |
| `lo` | `{item: best\|last}`(F1 낮은 쪽, 같으면 last) |
| `rule3` | `{ck: {item: {벌: [tp, fn, fp]}}}` 또는 null |
| `phase` | **계약 v1(새).** `meta.phase` 그대로(없으면 null). `results_newdata.run()` 1줄 |

- 점수 카드 `score`: 침입 · 배회 · 방화는 공식 점수 최고값(같으면 늦게 끝난 판) `{item, f1, exp, ck, tp, fn, fp, judge}`. 쓰러짐은 `fall_ref`
- 부작용: 학습 서버에서는 이 GET 이 `run_info.json` 을 만들 수 있음

### 4-8. 동률 규칙

- 판마다 항목별 `lo` 체크포인트의 정검 수 차이(대조군 대비)를 더한다
- 합의 절댓값이 2 미만이면 `동률`, 양수면 `개선`, 음수면 `하락`
- 모델 고르기 규칙(ML): 채점편 `min(best, last)` 정검 합 +2편 이상 · 안 본 편 동등 이상 · 동률이면 싼 쪽. 화면은 계산을 재현하지 말고 `verdicts` 값만 보여 준다

---

## 5. 예측 출력 형식

### 5-1. 단위 · 좌표

| 대상 | 규약 |
|---|---|
| 시각 | 영상 시작부터 초. 정답 시각은 정수 초 |
| 라벨 저장소(손라벨 · SAM · 정답라벨) | 0 ~ 1 정규화 `[x, y, w, h]`. x, y 는 좌상단 |
| 예측 · 덤프 | 원본 프레임 픽셀 `[x1, y1, x2, y2]`. 배포 영상은 1280x720 |
| 구역 다각형 | 픽셀 정수 `[[x, y], …]` |
| YOLO txt | `cls cx cy w h`, 정규화(중심 좌표) |

### 5-2. 채점식(`kisa_items.score`)

- 정답 창 = 정답 −2초 ~ +10초(`BEFORE_S = 2.0`, `AFTER_S = 10.0`, `T_EPS = 0.2`)
- 창 밖 경보는 오검, 그 정답은 미검(틀린 시각 경보는 두 번 감점)
- F1(정검 · 미검 · 오검을 하나로 합친 점수) `= 200·tp / (2tp + fn + fp)`. 90 이상 합격
- 표본 간격 `SAMPLE_STRIDE_S = 0.5`(채점기와 덤프가 같아야 함). 09-30 새 기준선은 초당 6장(판정기 쪽)

### 5-3. 검수 캐시 `dumps/review/<판>/<ckpt>/<item>/`

- `<ckpt>` ∈ `best` · `last` · `배포`(쓰러짐 `falldown_deploy/배포`) · `<ck>+<기술id>`. `<item>` ∈ `fire` · `intrusion` · `loitering` · `falldown`
- 클립마다 `<클립>.json`, 끝나면 `summary.json`, 계산 중 `_progress.json = {done, total}`
- 쓰는 곳: 작업 PC `pc_review.py`(채점과 한 번에). `scripts/review_cache.py` 서버 루프는 꺼짐(`--fall` 로 쓰러짐만). 기술 결과는 `scripts/review_post.py`

`<클립>.json`:

| 키 | 타입 | 뜻 |
|---|---|---|
| `clip`, `item` | str | 클립 이름, 항목 |
| `res` | int | 추론 해상도(학습 해상도) |
| `stride` | float | 표본 간격 초(0.5, 쓰러짐 0.1) |
| `wh` | [W, H] | 원본 프레임 크기(1280, 720) |
| `zone` | [[x, y]] 또는 null | 판정기가 쓴 구역(픽셀). 방화 · 쓰러짐은 null |
| `conf` | float | 규칙 문턱(침입 0.45, 배회 0.40, 방화 0.40, 쓰러짐 0.80) |
| `smoke` | float 또는 null | 방화 연기 문턱(1.1 = 사용 안 함) |
| `samples` | list | 아래 표 |
| `signal` | list | 아래 표 |
| `alarm` | float 또는 null | 예측 경보 시각(onset + delay, 소수 2자리) |
| `alarm_raw` | float | 작업 PC 판에만. 반올림 전 값 |
| `gt` | int 또는 null | 정답 첫 경보 시각 |
| `verdict` | str | `정검`, `미검`, `오검` |
| `wmtime` | int | 가중치 mtime(최신 여부 판정) |
| `where` | str | 계산한 장비(`서버 A`, `작업 PC`, `서버 B`) |
| `variant` | str | 기술 결과에만 |

| 항목 | samples | signal |
|---|---|---|
| 침입 · 배회 | `[[t, [[번호, conf, x1, y1, x2, y2]]]]` | `[[t, 구역 안 최고 conf]]` |
| 방화 | `[[t, [[cls, conf, x1, y1, x2, y2]]]]` (cls 0 불, 1 연기. conf 0.05 부터 저장) | `[[t, 불max, 연기max]]` |
| 쓰러짐 | `[[t, [[0, conf, x1, y1, x2, y2]]]]` (자세 모델 사람 박스) | `[[t, 0.5초 창마다 사람별 확률 최고]]` |

좌표는 소수 1자리, conf(confidence, 확신도) 는 3자리 반올림.

`summary.json`:

| 키 | 뜻 |
|---|---|
| `exp`, `ckpt`, `item`, `res` | 판 정보 |
| `weights` | 서버 절대경로 |
| `where`, `weights_mtime`, `made` | 계산 장비, 가중치 mtime, 만든 시각 KST |
| `clips` | `{클립: {alarm, gt, verdict, (alarm_raw, last)}}` |
| `score` | `{정검, 미검, 오검, 점수}` |
| `minutes` | 걸린 분 |
| `variant`, `base` | 기술 결과에만. `base = "<exp>\|<ck>"` |

판정기 기술 결과 `+<id>`(`scripts/review_post.py`):
- 상위 3개 판의 캐시 표본을 다시 판정만 해서 `<ck>+<id>/` 에 같은 모양으로 씀. `summary.weights_mtime` 이 원래 캐시와 같아야 최신(`is_fresh`)
- 등록 기술은 침입만(`VARIANTS["intrusion"]`): `seam`(조각 정리), `contain`(겹침 제거), `seamB`, `seamBstill`, `seam8`, `trk`(번호 거리 한도), `seam8trkfoot`
- 디스크의 `+seam8trk`, `+seam8trkcut` 은 등록에서 빠진 고아

### 5-4. `dumps/ruleeval/rule3.json`(결과 탭 '3규칙 F1'. 쓰는 곳 B `rule3_export.py`)

| 키 | 타입 | 뜻 |
|---|---|---|
| `made` | str | 만든 시각 KST |
| `rate` | str | `"초당 2장 · 시작 0"` |
| `picks` | dict | `{intrusion: {G, B, B+S, T}, loitering: {G, B, T}, fire: {B, T}}`. 값은 규칙 키 문자열, 방화 B 는 null |
| `runs` | dict | `{<판>: {<best\|last>: {<item>: {<벌>: [정검, 미검, 오검]}}}}` |

벌: G = 안내서 정의 그대로, B = G + 추적 · 검출 끊김 유예, T = 지금 판정기 규칙, +S = 타일 경계 조각 정리(침입만).

| 항목 | 규칙 키 형식 |
|---|---|
| 침입 | `conf\|꼭짓점\|hold초\|끊김초\|추적초\|궤적\|조각정리` (예 `0.45\|3\|1.0\|1.0\|5.0\|0\|0`) |
| 배회 | `conf\|꼭짓점\|체류초\|끊김초\|여유px\|늦게 온 일행초` |
| 방화 | `문턱\|창초\|필요초` |

`b_eval_20260930/` 안: `results/summary.{md,json}`, `results/intr_rd.json` · `loi_rd.json` · `fire.json` · `fire_epochs.json`(규칙키 → `[tp, fn, fp]` 또는 헛경보 편 수), `lists/`(`fp_ind.txt` 헛불 38편, `unseen_intr.txt` 117, `unseen_loi.txt` 273, `unseen_loi_sub.txt` 91, `official.json`), `dumps/{intr,loi,fire}/<모델>/…/<클립>.json`. `<셋>` ∈ `score`(채점편) · `rd`(안 본 편) · `fp45`(헛불 판단용). 전부 KISA 파생.

### 5-5. 그 밖의 덤프

| 덤프 | 쓰는 곳 | 형식 | 단위 · 좌표 |
|---|---|---|---|
| `dumps/intrusion_*/<클립>.jsonl` | `person_redump.py` | `{"t": 초, "boxes": [[번호, conf, x1, y1, x2, y2]]}` | 0.5초, 픽셀 |
| `dumps/loiter_*/<클립>.jsonl` | `server_tdump.py` | 같은 모양. BoT-SORT(추적기) 번호, 좌표 정수 | stride 인자 |
| `dumps/fire_box/<판>/<클립>.jsonl` | `exp_boxdump.py`(`/api/boxdump_start`) | `{"t", "boxes": [[cls, conf, x1, y1, x2, y2]]}`. 진행 중 `.jsonl.part`, `.progress = {done, total}` | 0.5초, 픽셀, conf ≥ 0.10 |
| `dumps/score_tl/<태그>.json` | `score_kisa.py` | `{클립: {rows: [[t, 불max, 연기max]], gt: int}}` | 0.5초 |
| `dumps/fall_seq_*/<클립>.json` | `fall_sweep.py` 등 | `{imgsz, fps, curves: [[[t, logit], …] 트랙별], (gt, gt_end, tod, fold)}` | t = 창 마지막 0.5초 슬롯 시작, logit = 시그모이드 전 값 |
| `dumps/bench_all.json` | `/api/bench` | 속도 표 | ms |
| `dumps/vid_safe/data/원본데이터/…/<클립>.mp4` | `/vid/?safe=1` | 다시 인코딩한 시청용 사본 | |

### 5-6. SA XML(`kisa_items.sa_xml`, 안내서 형식 그대로)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<KisaLibraryIndex><Library><Clip>
  <Header><AlarmEvents>1</AlarmEvents><Filename>C00_001_0001.mp4</Filename></Header>
  <Alarms><Alarm>
    <StartTime>00:03:01</StartTime><AlarmDescription>Loitering</AlarmDescription><AlarmDuration>00:04:03</AlarmDuration>
  </Alarm></Alarms>
</Clip></Library></KisaLibraryIndex>
```

- 경보 없음 = `<AlarmEvents>0</AlarmEvents>` + 빈 `<Alarms></Alarms>`(자기닫힘 태그 안 씀)
- `StartTime = hms(onset + delay)` 정수 초 반올림. `AlarmDuration` = 경보부터 영상 끝까지
- 실행 한 번에 항목 하나만. 파일은 `--out/<영상stem>.xml`(기본 `_kisa_port/KISAresult`). 시험 PC 결과는 `KISAresult/<쓰러짐|방화|침입|배회>/<stem>.xml` → zip → `exam_ingest.py` → `results/exam_pc_<run>/<항목>/`

### 5-7. 판정기 stdout 줄(로그 · 대시보드가 읽음)

- 첫 줄 `[설정] 항목=intrusion 모델=… 주기=0.5s 해상도=960 타일=3x3 겹침=0.2 conf=0.45 꼭짓점=3 연속=2 끊김허용=2 확정대기=24.0s`
- 진행 `[클립] <파일> 시작` · `[진행] <파일> <초>초` · `  <파일> → SA HH:MM:SS (확정)` / `(영상끝 미확정)` / `SA 없음` · `SA N건 → <out> (n프레임, Ns)`
- 편별 `  클립 <stem>: <정검|미검|오검> (gt=<int|None> sa=<소수1자리|None>)`
- 마지막 `[<item>] 정검 a 미검 b 오검 c → 점수 F.FF 합격` 또는 `(90 미달)`

### 5-8. 판정 상수(`_kisa_port/tools/kisa_items.py ITEMS`, 배포값. 화면 설명용)

| 항목 | 주요 값 |
|---|---|
| intrusion | stride 0.5, delay 0, conf 0.45, corners 3, hold 2표본, settle 24초, gap 2표본. 타일 `grid 3, overlap 0.2, imgsz 960, conf 0.15`, 자체 IoU(Intersection over Union, 겹침 비율) 트래커 |
| loitering | stride 0.5, delay 10, conf 0.40, corners 0(발끝), dwell 6초, settle 5초, gap 10표본, margin 10px, track_imgsz 640, BoT-SORT(conf 0.20) |
| falldown | stride 0.1, delay 1, th 0.80, need 5창 연속, pose_imgsz 1280, net 3벌 |
| fire | 두 벌(표본마다 최고값), stride 0.5, delay 10, fire 0.40, smoke 1.1(안 씀), win 20표본 · hits 3. 6뷰(전체 + 4분할 + 가운데) |

- 09-30 판정기(시험 저장소)는 모델을 새 데이터 판으로 바꿨고 초당 6장 · 규칙 B(+S)가 새 기준선. 위 값은 이 저장소 채점 경로의 배포값이라 다를 수 있음 → 화면에 '판정기 설정' 으로 보여 줄 때는 `result_blocks.judge.applied` 를 쓴다

---

## 6. 라벨 · 미디어 경로

### 6-1. `data/원본데이터/`(git 제외, 읽기 전용)

| 폴더 | 내용 | KISA 제공 | `datasets.yaml use` |
|---|---|---|---|
| `kisa_배포_검증영상/` | `deploy_val/{방화(10개),침입(30개),배회(30개),쓰러짐(10개)}/배포/*.mp4+xml`, `zone_maps/*.map`(296). 채점 전용 | 예 | eval |
| `kisa_연구개발_방화영상/` | 방화 75편(mp4 + xml). 손라벨 원천 | 예 | train |
| `kisa_연구개발_사람영상/` | `1. 배회(325개)`, `2. 침입(170개)`, `4. 쓰러짐(330개)`, `zone_maps` | 예 | train |
| `KISA_악천후_사람/` | 사람 모델로 채점하지 않는 45편(싸움 · 유기 · 마케팅 · 쓰러짐) | 예 | train |
| `kisa_산불_정지이미지/`, `kisa_산불_합성영상/` | 합성(정답 없음) | 예 | train |
| `aihub171_이상행동/` | 배회 실외 야간(키프레임 점 + 행동 구간) | | train |
| `aihub71330_산불/`, `aihub71751_48k/`, `aihub71751_night_20260928/`, `aihub71953_다각도/`, `aihub_침입쓰러짐영상/` | AI허브 셋 | | train |
| `open_coco/`, `open_fasdd/`, `open_dfire/`, `open_azimjaan_fire/` | 공개셋 | | train |
| `open_datacluster_fire/`, `open_flir/`, `open_llvip/` | 라이선스 문제 | | none |

### 6-2. 라벨 저장소 `data/학습데이터/`

**`손라벨/{person,fire,image}_labels.json`**(`/api/savelabel` 이 씀. 행 배열)

| 키 | 타입 | 뜻 |
|---|---|---|
| `file` | str | 프레임 이름 `<클립>_<t 4자리>.png`. 이미지는 저장소 기준 경로 |
| `clip` | str | 영상 stem. 이미지는 `img:data/원본데이터/…` |
| `src` | str | `원본데이터` 기준 상대경로 |
| `t` | int 또는 float | 초. 프레임 단위로 고르면 소수 2자리 |
| `cls` | int | 0(사람 또는 불), 1(연기), **−1 = 검토 완료 · 객체 없음** |
| `x`, `y`, `w`, `h` | float | 0 ~ 1 정규화(소수 5자리). x, y 는 좌상단 |
| `W`, `H` | int | 원본 해상도 |
| `crop` | list | 항상 `[0, 0, W, H]` |
| `ts` | int | 저장 시각(epoch 초) |
| `obj` | int | 선택. 객체 번호 |
| `eval` | true | 선택. 채점 전용 행. 학습셋 빌더가 제외 |

- `손라벨/clip_state.json`: `{stem: {mark: "prop"|"hand", a: 초, b: 초, smoke: "todo"}}`. `/api/clipstate` POST 로 고침
- `자동라벨/sam2/<stem>.json`: `{clip, frames: {"190.5": {"<obj>": [x, y, w, h]}}, polys: {t: {obj: [[x, y], …]}}, seeds: [{t, obj, box}], updated}`. 0.5초 격자, 정규화 좌상단. 손라벨 박스가 있는 프레임은 저장 안 함
- `정답라벨/<stem>.json`(`derive_gt`, `/api/gtlabel` 첫 읽기 때 생성): `{clip, frames, points, actions: {obj: [{name, start, end}]}, events: [{name, start, dur, note?}], derived: true, src: kisa_xml|aihub171|aihub_json|aihub71953, src_file, (W, H, fps, meta, note)}`
- `정답라벨/_gt_정정.json`: 원본 StartTime 이 틀린 3편의 정정값

### 6-3. 학습셋 `data/학습데이터/trainset_<mode>_<날짜>/`

- `{images,labels}/{train,val}/`, `train.txt`, `val.txt`(절대경로 목록), `data.yaml`(`path, train, val, nc, names`), `meta.json`
- 프레임 jpg 이름 `<클립>_<t×10 다섯자리>.jpg`(예 `E02_002_00660.jpg` = 66.0초). 이미지 셋은 원본 심링크
- YOLO txt 한 줄 `cls cx cy w h`(정규화, 소수 6자리). 빈 파일 = 배경. 방화 `['fire','smoke']`, 사람 `['person']`
- `meta.json`(빌더 판) 키: `name, mode, built, train, val, priority("hand > sam > gt"), excluded, sam_anchor, neg_from, marker_rule, stats, contract`. 파생 셋은 `source, counts, bg_ratio, kisa_ratio, val_for_checkpoint, snapshot, corrections` 등. 결과 탭은 `stats` 의 `이미지:` · `영상프레임:` 키로 구성을 펼친다
- 검증셋: `val_domain.txt`(자체 CCTV 프레임, 학습 클립 통째로 제외) → 100장 미만이면 `val_small`(600장, 겹침). `evalset_*` 는 mAP 측정 전용, val 금지
- 채점 측정 전용 `evalset_fire/`, `evalset_person/`

### 6-4. `configs/datasets.yaml`(데이터 계약, git 추적)

`<카테고리>: {mode: fire|person, media: video|image, gt: kisa_xml|aihub171_xml|aihub_json|aihub71953_json|yolo_txt|coco_json|voc_xml|none, classes: {원본: 우리|drop}, use: train|eval|none, note}`. POST `/api/datasets` 가 이 파일을 직접 고친다(ML 소유. 화면 기능 확대 금지).

### 6-5. KISA 구역 `.map` · 정답 XML

- `.map`(296): 뿌리 `<DA>`, 자식 `<DetectionAreas>`, `<DetectArea>`, 선택 `<Intrusion>`(57) · `<Loitering>`(97) · `<PeopleCountingA/B>` · `<Queueing>`. 각 영역 `<Point>x,y</Point>` 목록, 1280x720 픽셀 정수. 파일은 클립 이름 앞 두 마디(`C00_140_0001` → `C00_140.map`)
- 파서: `kisa_items.zone_of` = tag 영역 → DetectArea → 화면 전체. `build_dash_meta.zone_of` = 배회는 `Loitering`, `Intrusion` 순
- 정답 XML: `KisaLibraryIndex/Library/{Scenario, Dataset, Libversion, Clip/Header/{Filename, Stage?, Duration, AlarmEvents, Location, Weather/{TimeOfDay, Clouds, Windy, Rain, Snow, Fog}, Distraction, DetectionAreas, DetectArea/Point*, Intrusion|Loitering/Point*}, Clip/Alarms/Alarm/{StartTime HH:MM:SS, AlarmDescription, AlarmDuration HH:MM:SS}}`
- 파서: `kisa_items.read_alarms` → `{start_s, desc}`, serve `fire_spans` → `{start, dur, kind}`, serve `clip_conds` → `{tod, gt, snow, rain, fog, loc}`
- 정답 XML 에 구역 다각형이 들어 있어 검수 · 결과 파일 전부 KISA 파생

### 6-6. `dash_v2/dash_meta.json` · `dataset_meta.json`(git 제외, 손으로 생성)

- `dash_meta.json`(`build_dash_meta.py`, 09-16 판): `{items: {fire|intrusion|loiter|fall|labelset: {title, rows}}}`. 행 키 `name, video(저장소 상대 mp4), gt(초), gt_dur, tod, weather([Snow|Fog|Rain]), signal_type, sa`. 항목별 추가: fire `signal, tracks, framew, frameh` / intrusion · loiter `zone, zone_tag, detect, tracks, signal, framew, frameh` / fall `curves` / labelset `frames, box_count, frame_count`
- `dataset_meta.json`(`build_dataset_meta.py`): `{datasets: [{key, title, rel, classes, total, shown, labeled_ratio, images: [{file, stem, labeled, rel}]}]}`. 셋당 최대 600장
- 재생성은 ML(`ml_changelog` 트리거 표)

### 6-7. 미디어 · 라벨 엔드포인트

| 경로 | 하는 일 |
|---|---|
| GET `/vid/<저장소상대>.mp4[?safe=1]` | Range(206) 스트리밍, no-store. `safe=1` 이면 `dumps/vid_safe/<같은 경로>`. 디코딩 오류 3 이면 화면이 safe 로 이어 재생 |
| GET `/frameat?clip=&t=&w=` | 그 시각 프레임 JPEG. clip 은 원본데이터 기준, 확장자 없음. 캐시 씀 |
| GET `/api/warmframes?clip=&ts=a,b&w=` | 프레임 미리 캐시 `{warmed, total}` |
| GET `/dsimg/<상대>` | 이미지 |
| GET `/dslabel/<상대>.txt` | YOLO txt |
| GET `/frame/<이름>.png` | `손라벨/full` 에서, 없으면 손라벨 행의 src · t 로 추출 |
| GET `/api/rawlabel?rel=` | 원본 정답을 YOLO 줄로(datasets.yaml 변환) |
| GET `/api/clipinfo?clip=` | `{clip, fps, frames, dur, W, H, fire: [{start, dur, kind}]}` |

---

## 7. 히스토리 계약(계약 v2)

### 7-1. 원본 · 권한

| 것 | 내용 |
|---|---|
| 원본 | 서버 B `configs/history.yaml`. 편집은 B 대시보드 화면(사용자) 과 B `/api/history` POST(ML, daily-report 스킬)만 |
| 사본 | 서버 A `configs/history.yaml` = 커밋용. A 화면은 `readonly: true` |
| 편집 가능 조건 | 서버 프로세스 환경변수 `VMS_HISTORY_EDIT == "1"`(B 는 `dash.sh` 가 켬. A 는 없음) |
| 범위 | 모델 · 데이터 · 체크포인트 · 판정 규칙 실험과 그 할 일만. 대시보드 요청 · 운영 · 문서 정리는 안 담음(`ml_changelog.md` 요청 절) |
| 규모 | 10-01 11시 기준 5일 · 43항목(전부 `item` 없음 → 소급 예정) |

### 7-2. 파일 스키마

| 위치 | 키 | 타입 | 뜻 |
|---|---|---|---|
| 최상위 | `updated_at` | str | `YYYY-MM-DD HH:MM:SS` KST |
| 최상위 | `updated_by` | str | 마지막 저장자 |
| 최상위 | `days` | list | 날짜 내림차순 |
| day | `date` | str | `YYYY-MM-DD`. **따옴표로 저장**(손 편집으로 따옴표가 빠지면 일지 동기화가 그날을 비움) |
| day | `note` | str | 선택 |
| day | `milestones` | [{at, text}] | 선택. 이정표 |
| day | `items` | list | |
| item | `id` | str | 고유. ML 은 `h<MMDD><a..>`(예 `h0930ad`), 화면 새 항목은 `h<MMDD>_<base36>` |
| item | `s` | str | 상태(필수). **v2: `아이디어` · `할 일` · `진행` · `완료`** |
| item | `dec` | str | 판정. `s == 완료` 일 때만. `채택` · `기각` · `보류` |
| item | `t` | str | 제목(필수). 제목만 보고 무슨 작업인지 알게 |
| item | `why`, `sub`, `ref`, `cond`, `carry` | str | 판정 이유, 결과 수치, 기록 위치(`" · "` 로 나누면 태그), 선행 조건, 넘어감(`→ 09-30`) |
| item | `item` | str | **v2(새).** `방화` · `사람` · `쓰러짐` · `공통`. 없으면 공통 |
| item | `phase` | str | **v2(새).** `phases` 코드. 없으면 그리드 밖 |

- 파일 머리 `#` 주석 줄은 저장 때 보존
- 서버 상수(풀스택이 바꿈): `HS_KEYS = id, s, dec, t, why, sub, ref, cond, carry, item, phase` · `HS_ST = 아이디어, 할 일, 진행, 완료` · `HS_DEC = 채택, 기각, 보류` · `HS_ITEM = 방화, 사람, 쓰러짐, 공통`(새) · `CONTRACT_VER = 2`(새, 정수)
- `_hs_clean` 추가 2줄: `item` 은 없거나 `HS_ITEM` 안, `phase` 는 없거나 `result_blocks.yaml phases` 키 안. 그 밖은 지금처럼(모르는 키 버림 · 빈 값 제거 · `t` · `id` 필수 · 날짜 정규식 · 같은 날짜 · 같은 id 거부)

### 7-3. 칸반 매핑

| 칸반 열 | `s` | `dec` |
|---|---|---|
| Backlog | `아이디어` | 없음 |
| To-Do | `할 일` | 없음 |
| In Progress | `진행` | 없음 |
| Done | `완료` | 채택 · 기각 · 보류 |

- 배지: `item`(없으면 공통) · `phase`(이름표 그대로, 없으면 표시 안 함) · `dec`
- 전역 필터(2절 UI 열)가 켜지면 `item` 이 같은 항목 + 공통만
- 일지 동기화(`sync_history.py`)는 진행 → 할 일 → 완료 → 아이디어 순으로 그림. 아이디어는 맨 아래

### 7-4. Quick Add 규약

- 쓰는 키 셋만: `{id, s: "아이디어", t}`. 전역 필터가 항목이면 `item` 도
- `id` 는 화면 규칙 `h<MMDD>_<base36>`, 오늘 day 에 넣음(없으면 day 생성)
- 범위 = 모델 개선 아이디어만. 대시보드 요청은 `ml_changelog.md` '풀스택 → ML 요청' 절
- 아이디어 → 할 일로 올릴 때 `cond` · `item` · `phase` 를 채우는 건 ML(스킬 규칙)

### 7-5. GET · POST

- GET `/api/history` → 파일 문서 + `readonly: bool`. date · updated_at 은 문자열, 날짜 내림차순. 파일 없으면 `{error}`
- POST `/api/history` 본문 `{base: <읽었을 때 updated_at>, by: "사용자"|"Claude", doc: {days: […]}}`. 처리 순서:
  1. 읽기 전용 서버면 `{ok: false, err: "이 서버는 히스토리를 보기만 합니다…"}`
  2. `_SAVE_LOCK` 안에서 파일 다시 읽음. `str(base)` ≠ 현재 `updated_at` 이면 `{ok: false, conflict: true}` → 화면은 다시 불러오고 입력 버림
  3. `_hs_clean` 검증 실패 `{ok: false, err: "ValueError: …"}`
  4. 저장: `updated_at` = 지금 KST, `updated_by` = `by`(없으면 사용자). `yaml.safe_dump(allow_unicode, sort_keys=False, width=100000)` + `.yaml.tmp` 원자 교체
  5. `{ok: true, doc: <다시 읽은 문서>}`
- `doc.days` 밖의 키는 무시. 충돌 시 사용자가 고친 값은 그대로 두고 다시 올린다

### 7-6. 운영 · 소급

- ML 순서: B GET → 수정 → POST(충돌이면 다시) → B 파일을 A `configs/history.yaml` 로 복사 → `[ml]` 커밋 · 푸시 → `sync_history.py <날짜>`
- 기존 34항목 `item` 소급은 ML 이 B API 로. 단 **풀스택이 v2 서버를 B 에 올린 뒤**(그 전엔 `_hs_clean` 이 `item` · `phase` 를 버림)
- `ml_changelog.md` 확인 규칙: 풀스택이 계약 항목을 반영하면 그 항목 아래 `확인: YYYY-MM-DD dash_v2 <커밋 7자>` 한 줄 + 머리 `미확인:` 에서 번호 제거 + `serve_kisa.py` 의 `CONTRACT_VER` 를 그 번호로. `scripts/check_contract.py`(ML, 읽기 전용) 가 `serve_kisa.py` 본문의 `CONTRACT_VER = N`(정수) 줄을 읽어 changelog 맨 위 번호와 대조(상수가 없으면 경고만)

---

## 8. 탭 ↔ 엔드포인트

### 8-1. 지금 탭 ↔ 계약 v2 뒤 ↔ 엔드포인트

| 지금 탭(`main.js buildMode`) | 계약 v2 뒤(풀스택이 구현) | 주 엔드포인트 |
|---|---|---|
| 데이터 확인 `data` | 그대로 | `/api/sources` `/api/raw` `/api/clips` `/api/clipconds` `/api/clipinfo` `/api/dataset` `/api/datasets` `/api/catmode` `/api/clipstates` `/api/clipstate` `/api/refresh_cache` `/api/pushinfo` `/api/push_labels` + 편집기 · SAM2 묶음 |
| 영상 검수 `review` | 전역 필터 연동. 그룹 이름표 = 블록 `label` + `phases` 이름표(은어 없이) | `/api/review_models` `/api/review_summary` `/api/review_clip` `/api/meta` `/vid` `/frameat` `/api/gtlabel` `/api/labels` |
| 결과 `results` | 전역 필터. 판 배지 `runs[].phase` → `phases` 이름표. 용어 토글 = `terms` | `/api/result_blocks` `/api/queue`(30초) `/api/bench` |
| 히스토리 `history` | 칸반 4열 + Quick Add + `item` · `phase` 배지 + 전역 필터. B 만 저장 | `/api/history` GET · POST |

- 전역 필터 값: 화재 · 배회·침입 · 쓰러짐(2절 표). 상태는 `core.js` 전역 + localStorage(마지막 탭과 같은 방식)
- 서버 이름표 `#host` 는 `js/host.js`(git 제외)

### 8-2. 엔드포인트 전체

정적: GET `/`, `/index.html`(dashboard.html), `/js/<이름>.js`

데이터 확인:

| 메서드 | 경로 · 인자 | 읽기/쓰기 | 하는 일 |
|---|---|---|---|
| GET | `/api/sources` | 캐시 씀 | `[{key: 카테고리, count}]`(`_cache/sources.json`) |
| GET | `/api/raw?src=&limit=600` | 캐시 씀 | `{cat, img_total, vid_total, images: [표본], videos: [전부]}` |
| GET | `/api/clips?src=` | 읽기 | `원본데이터` 기준 mp4 목록(확장자 없음) |
| GET | `/api/clipconds?src=` | 읽기 | `{stem: {tod, gt, snow, rain, fog, loc}}` |
| GET | `/api/dataset` | 읽기 | dataset_meta.json |
| GET | `/api/datasets` · `/api/catmode` | 읽기 | `{카테고리: cfg}` · `{cat: mode}` |
| POST | `/api/datasets`, `/api/catmode` | **`configs/datasets.yaml` 씀** | `{cat, mode?, media?, gt?, classes?, use?, note?}`. null 이면 필드 삭제 |
| GET | `/api/clipstates` | 읽기 | clip_state.json |
| POST | `/api/clipstate` | clip_state.json 씀 | `{clip, mark?(base\|prop\|hand), a?, b?, smoke?}` |
| POST | `/api/refresh_cache` | 캐시 비움 | `{ok, sources}` |
| GET | `/api/pushinfo` | 읽기 | `{enabled, target}`(호스트 이름만) |
| POST | `/api/push_labels?dry=1` | rsync + merge_labels | `{ok, dry, log}`. `LABEL_PUSH_TARGET` 작업대만 |

편집기 · 라벨:

| 메서드 | 경로 · 인자 | 읽기/쓰기 | 하는 일 |
|---|---|---|---|
| GET | `/api/labels?kind=person\|image\|(fire)` | 읽기 | 손라벨 배열 |
| POST | `/api/savelabel` | 손라벨 씀, SAM 프레임 뺌 | `{clip, t, src, file, W, H, boxes: [[cls, x, y, w, h, obj?]], kind, clear, eval}` → `{ok, total, labels}`. 박스 0개 = cls −1 |
| POST | `/api/clearlabels` | 손라벨 · SAM 지움 | `{clip, kind}` → `{ok, hand_rows, sam_frames}` |
| GET | `/api/gtlabel?clip=` | **정답라벨 복사본 생성** | 정답라벨 JSON |
| GET | `/api/config` | 읽기 | `{prop_default, prop_thr}` |

SAM2:

| 메서드 | 경로 | 요청 → 응답 |
|---|---|---|
| POST | `/api/sam2_mask` | `{clip, t, pts: [[x, y, 1\|0]], box?}`(정규화) → `{box, poly, score}`. 저장 없음 |
| POST | `/api/sam2_propagate_start` | `{clip, seeds: [{t, box, obj, pts?}], a?, b?, step = 0.5, mode?}` → `{id}` 또는 `{err}` |
| GET | `/api/sam2_jobs?clip=` | `[{id, clip, state: queued\|running\|done, pos, done, total, err, warn, saved, sec, nframes, mode, drops, a, b, step, seed_ts}]` |
| POST | `/api/sam2_cancel` · `/api/sam2_clear` · `/api/sam2_drop` · `/api/sam2_drop_obj` | `{clip}` / `{clip, t}` / `{clip, obj}` → `{ok, …}` |
| GET | `/api/sam2label?clip=` · `/api/sam2frames` | SAM 저장소 · `{stem: [t…]}` |

검수:

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| GET | `/api/review_models?item=` | `{models: [{key, exp, ckpt, res, data, ended, done, progress, score, official, (ckLabel, variant, base)}], groups: [{id: "_top", label, keys}, {id, label: "[날짜] 제목", runs}]}`. 대상 = `review_cache.eligible()`(status trained · ended · best_pt · 모델 yolo · 항목 방화/사람/침입/배회 · '지금 데이터'). 쓰러짐 고정 `falldown_deploy\|배포` |
| GET | `/api/review_summary?key=&item=` | `summary.json` + `official: {점수, 정검, 미검, 오검}` + 클립별 `official`. 없으면 404 |
| GET | `/api/review_clip?key=&item=&clip=` | 클립 JSON 그대로(5-3). 없으면 404 |
| GET | `/api/meta` | dash_meta.json |
| GET | `/api/boxmodels` · `/api/boxdump?exp=&clip=` | 옛 오버레이 목록 · `{state, rows?, pct?}` |
| GET | `/api/boxdump_start?exp=&clip=` | **GPU 추론 시작** |

- key 형식 `<판>|<ck>`. 판 이름 `^[A-Za-z0-9_.\-]+$`, `ck` ∈ `best` · `last` · `배포` + 선택 `+<영문 기술id>`, `item` ∈ `fire` · `intrusion` · `loiter` · `fall`
- 화면: 재생바에 정답 유효창(−2 ~ +10초) · 신호(사람 회색 = 화면 전체 최고 conf, 파랑 = 구역 안 / 방화 빨강 불 · 보라 연기 / 쓰러짐 확률) · 문턱 선 · 예측 경보. 영상 위 구역 다각형 + 박스(0.20 미만 안 그림, 문턱 이상 실선). 오른쪽 정답 · 예측 · 판정 · `공식: …` 불일치 태그

결과 · 히스토리:

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| GET | `/api/result_blocks` | 4-7 |
| GET | `/api/queue` | `{running, jobs: [{name, epoch, epochs, pct, it, its, it_s, elapsed, eta, mem, val: {n, P, R, map50, map5095}, epoch_min, remain_h, finish_kst, phase}], waiting: [{name, item, queue, imgsz, batch}], gpu: {used_mib, total_mib, free_mib, util}, runners, log}`. 준비 중이면 `{name, state: "준비 중(라벨 스캔·캐시)"}`. B 는 비어 있음 |
| GET | `/api/bench` | `dumps/bench_all.json` |
| GET | `/api/results` | 옛 결과 탭. 화면은 안 부름 |
| GET · POST | `/api/history` | 7절 |

### 8-3. 읽기인데 쓰거나 계산하는 GET(자동 호출 금지 또는 주의)

| 엔드포인트 | 하는 일 | 규칙 |
|---|---|---|
| `/api/review_models?item=intrusion` | `review_post.compute_missing()` 백그라운드 CPU 계산 → `dumps/review/…+<id>/` 씀 | 사용자 동작으로만. 타이머 · 로딩 시 자동 호출 금지 |
| `/api/boxdump_start` | GPU 추론(`exp_boxdump.py`) | 사용자 동작으로만 |
| `/api/result_blocks` | 학습 서버에서 `run_info.json` 씀 | 허용(설계된 부작용) |
| `/api/gtlabel` | 정답라벨 복사본 씀 | 허용 |
| `/frameat`, `/api/warmframes` | 프레임 캐시 씀 | 허용 |
| `/api/sources`, `/api/raw` | `_cache` 씀 | 허용 |

---

## 9. UI 문구 규칙

### 9-1. 규칙

- 은어 금지: 큐 이름 · 셋 이름 · 변수 이름을 화면에 그대로 쓰지 않는다. 예 "눈배경7편" → "악천후 눈 영상 7편"
- 단계 이름표는 `phases` 값 그대로(한 글자도 안 바꿈). 코드 `grid1` 은 화면에 안 보임
- 데이터 이름은 `result_blocks.yaml terms` 의 `d` 로 풀이(용어 토글). 셋 이름 원문은 툴팁 · 보조 표시
- 배지 · 태그 · 불릿 · 표만. 서술문 금지. 표 머리말 금지. 상태와 날짜는 칸을 나눔
- 숫자는 원본 값 그대로(반올림 · 재계산 · 추정 금지). 없으면 "없음"
- 블록은 독립변수 · 종속변수 · 통제 변수를 칸으로 명시(`iv` · `dv` · `same_data`). 제목은 'A vs B'
- 약어는 첫 등장 풀이 또는 용어 토글
- 장비 이름(`where` 의 "작업 PC")을 화면 라벨에 그대로 쓰지 않는다 → "공식 채점 장비". "서버 A" · "서버 B" 는 그대로
- 색 · 아이콘만으로 뜻을 전하지 않는다(판정 글자 함께)

### 9-2. 내부 용어 → 화면 문구

뜻 칸은 ML 이 아는 범위. `terms` 에 같은 용어가 있으면 그 `d` 가 우선.

| 내부 용어 | 뜻 | 화면 문구(배지 · 태그) |
|---|---|---|
| 판 | 학습 1회의 결과(실험 폴더 이름) | 실험 |
| grid · grid0 ~ 4 | 09-28 단계별 비교 계획 | `phases` 이름표 그대로 |
| hnfix | 사람 손라벨 스냅샷 계열(09-27, 하드네거티브 정정 뒤). '지금 데이터' 판의 기준 | `terms` 풀이. 없으면 "손라벨 데이터(09-27 정정판)" |
| hn | 하드네거티브(hard negative, 모델이 틀리기 쉬운 음성 사진) | "오검 유발 사진 포함" |
| bg10 · bg28 · bg41 | 학습셋의 배경(사람 · 불 없는) 사진 비율 % | "배경 10%" |
| comp / mask | 학습셋 이름 접미사(라벨 · 합성 방식 구분) | `terms` 풀이 그대로 |
| x2 · x<배율> | 오버샘플 배율(목록에 경로 반복) | "손라벨 2배 반복" |
| fog3 · snowbg · nightneg · notiny · clean | 합성 · 음성 · 제외 셋 이름 | "안개 합성" · "눈 배경 합성" · "야간 음성 사진" · "작은 사람 제외" · "군중 제외" |
| best / last | ckpt. best = 검증 mAP50-95 최고 에폭, last = 마지막 에폭 | "검증 최고(best)" · "마지막 에폭(last)" |
| epochN.pt | 0부터 센 파일 이름. `results.csv` 에폭 = N+1 | "에폭 N+1" |
| G / B / T | 규칙 벌. 안내서 그대로 / 끊김 유예 / 현재 판정기 | "안내서 그대로(G)" · "끊김 유예(B)" · "현재 판정기(T)" |
| +S | 타일 경계 조각 정리(침입만) | "조각 정리 적용" |
| 정검 / 미검 / 오검 | 정답 창 안 경보 / 놓침 / 헛경보(KISA 용어) | 그대로 + 용어 토글 풀이 |
| F1 · 점수 | `200·tp/(2tp+fn+fp)`, 90 이상 합격 | "점수(F1)" + 합격선 90 표시 |
| 채점편 · 채점 10편 · 30편 | KISA 배포 검증 영상(방화 10 · 침입 30 · 배회 30 · 쓰러짐 10). 측정만 | "인증 채점 영상 N편" |
| 안 본 편 · rd · unseen | 학습에 안 쓴 연구개발 영상(침입 117 · 배회 91 또는 273) | "학습에 안 쓴 영상 N편" |
| 헛불 38편 · fp45 | 불 없는 악천후 영상(헛경보 확인용) | "불 없는 영상 38편(헛경보 확인)" |
| 눈배경7편 | 눈 오는 악천후 영상 | "악천후 눈 영상 7편" |
| 변별 편 · key_clips | 판 사이 결과가 갈리는 방화 4편 | "판을 가르는 영상 4편" |
| 대조군 · control | 블록의 기준 실험 | "기준 실험" |
| 교란 변수 · declared false | `vary` 에 선언 안 된 설정 차이 | "통제 안 된 설정 차이" |
| 동률 / 개선 / 하락 | 정검 합 차 2편 미만이면 동률 | 그대로 + "(정검 차 N편)" |
| 지금 데이터 · new | 09-26 이후 손라벨(hnfix 계열)로 학습한 판 | "최신 데이터" |
| others | 블록에 없는 실험 | "비교 블록 밖 실험" |
| official · 작업 PC 점수 | 공식 채점 점수(`score.txt`) | "공식 점수" |
| score(캐시) | 검수 캐시 점수(`summary.json`) | "검수 점수" |
| 초당 6장 · r6p0 · 6p0 | 표본 간격 1/6초(시작 프레임 0) | "초당 6장 판정" |
| 타일 · 3x3 | 화면을 9조각으로 나눠 추론(침입) | "9분할 추론" |
| 6뷰 | 전체 + 4분할 + 가운데(방화) | "6구역 추론" |
| 11n · 11s · 11m · 11x | YOLO11 모델 크기 | "모델 크기 n/s/m/x" |
| kdm · KD | 지식증류 학생 판 | "증류 학생(11m 티처)" |
| 기술 · variant · +seam | 판정기 후처리 기술(review_post) | "판정 기술: 조각 정리" 등 |
| cond | 선행 조건 | "선행 조건" |
| mAP50 · mAP50-95 | 검출 정확도 지표 | "검출 정확도(mAP50)" |
| conf | 확신도 문턱 | "확신도 0.45" |
| SA | 경보 결과 XML | "예측 경보" |

---

## 10. 하지 말 것

| 금지 | 이유 · 대신 |
|---|---|
| `data/` 아래에 새 쓰기 경로 추가(손라벨 · 자동라벨 · 정답라벨 포함) | 라벨 저장은 기존 엔드포인트가 이미 함. 새 파일 · 새 폴더 금지 |
| `/api/boxdump_start` · `/api/review_models?item=intrusion` 자동 호출(로딩 · 타이머 · 폴링) | GPU 추론 · 백그라운드 CPU 계산. 사용자 동작으로만 |
| KISA 파생 파일 커밋(`results/*` · `dumps/*` · `rule3.json` · 검수 json · 정답 XML 사본 · `dash_meta.json`) | 구역 다각형 · 정답 시각 포함. `.gitignore` 에 있어도 강제 추가 금지 |
| A 대시보드에서 히스토리 편집 · A 에 `VMS_HISTORY_EDIT` 켜기 | 원본은 B 하나 |
| `configs/history.yaml` 손 편집 · 커밋 | API 로만. 손 편집은 날짜 따옴표가 빠져 일지 동기화가 깨짐 |
| 큐 yaml(`configs/queue_*.yaml`) · `scripts/exp_queue.py` · tmux 러너 건드리기 | 돌고 있는 yaml 편집은 바이트 오프셋이 깨져 고아 프로세스 |
| `_kisa_port/` 수정 · 리팩터링 | 인증 제출 도구 |
| `scripts/` 수정 · 새 스크립트 · `dash_v2` 밖 폴더에 파일 생성 | ML 소유. 필요하면 `ml_changelog.md` 요청 절 |
| 경로 하드코딩(절대경로 · 서버별 경로 · 사용자 이름) | `VMS_ROOT` · 저장소 상대경로 · `scripts/kisa_paths.py` 상수 |
| `dash_v2/` 에 로그 · 데이터 파일 | `logs/dash/` 로. `check_layout` 7번 위반 |
| `pkill -f` | 자기 셸 · 러너를 죽임. pid 로만(`dash.sh stop`) |
| SAM2 전파 중 대시보드 재시작 | 전파 결과 유실. `/api/sam2_jobs` 에 `running` · `queued` 없을 때만 |
| `git add -A` · `git commit -a` · `[dash]` 아닌 접두어 · `dash_v2/` · `docs/dashboard.md` · `ml_changelog.md` 밖 커밋 | 경계 |
| `dash_v2/js/host.js` 를 B 로 복사 | 서버마다 다른 이름표 |
| `results/` · `dumps/review/` 를 풀스택이 복사 | ML 이 함 |
| 새 앱 · 새 프레임워크 · 새 DB · 빌드 도구 · 새 의존 패키지 | dash_v2 확장만. 파이썬 표준 라이브러리 + 순수 JS 유지 |
| `/api/datasets` POST 기능 확대 · `configs/datasets.yaml` 손 편집 | 데이터 계약은 ML |
| 결과 수치 재계산 · 반올림 · 추정값 표시 | 원본 값 그대로 |
| `dumps/review` · `summary.json` · `meta.json` · `score.txt` 스키마 변경 요청 없이 전제 바꾸기 | 작업 PC 스크립트 · 러너가 씀. 바꾸려면 요청 절 |
| 화면에 서버 주소 · 계정 · 키 노출 | 보안 |

---

## 11. 알려진 불일치

| # | 내용 | 풀스택 영향 |
|---|---|---|
| 1 | `results/SUMMARY.md` 가 사람 판 점수를 전부 `-` 로 냄(`build_summary.RE_PERSON` 이 작업 PC 형식 · 옛 사람 형식과 안 맞음). `score_pc.txt` 만 있는 방화 판은 목록에서 빠짐 | 화면은 SUMMARY.md 를 읽지 않음. 점수는 `review_cache.official()` 기준. 고치는 건 ML |
| 2 | `docs/file_path.md` 와 실제 위치가 다름: `loocv_results.json` 을 쓰는 스크립트는 보관 폴더로 이동(파일은 09-07 판), `rule3.json` · `fire_epochs*` 는 `results/` 가 아니라 `dumps/ruleeval/` | 경로는 이 문서(3-2 · 5-4) 기준 |
| 3 | `results_newdata.verdict()` 는 `meta.status == "done"` 인데 그 항목의 공식 채점이 없으면 KeyError → `/api/result_blocks` 전체가 `{error}`(가능성, 실측 아님) | 화면에서 `{error}` 처리. 재현되면 요청 절에 적을 것 |
| 4 | `dumps/review` 에 고아 폴더 `+seam8trk`, `+seam8trkcut`(`VARIANTS` 등록 밖) | `review_models` 목록에 안 나와야 정상. 지우는 건 ML |
| 5 | `check_layout` 이 못 잡는 배치 위반: `results/_exam_ref/`(기록 파일 없음), A 루트 디버그 jpg 12장 | 무시 |
| 6 | `docs/PROPOSALS.md` 의 best 기준 설명이 낡음("0.9·mAP50-95 + 0.1·mAP50"). 설치판은 mAP50-95 만 | 화면 설명에 옛 식을 쓰지 말 것 |
| 7 | `docs/EXPERIMENTS.md` 의 OOM(Out Of Memory, 메모리 부족) 회복 설명("batch 20% 축소")이 코드와 다름. 09-26 부터 같은 batch 로 재시도 | 큐 상자 설명에 반영 금지 |

덧붙임:
- 이름이 같은 `phase` 셋(4-2절 주의). 항목 이름 계층 불일치(2절)
- A 와 B 의 `results/` 폴더 수 · `SUMMARY.md` 판이 다름(B 는 ML 이 복사한 만큼만)
- `_hs_clean` 이 v2 전까지 `item` · `phase` 를 버림 → 소급 순서(7-6)

---

## 12. 풀스택 세션 첫 할 일(계약 v1 · v2 수용 순서)

| # | 할 일 | 끝난 기준 |
|---|---|---|
| 1 | `ml_changelog.md` 머리 `미확인:` 의 v1 · v2 항목 읽기(바뀐 것 · 영향 · 옮기기) | 이 문서 4-2 · 7-2 와 같은지 확인 |
| 2 | `dash_v2/serve_kisa.py`: `HS_ST` 에 `아이디어`, `HS_KEYS` 에 `item` · `phase`, `HS_ITEM` 신설, `_hs_clean` 2줄(`item` ∈ HS_ITEM 또는 없음, `phase` ∈ `result_blocks.yaml phases` 또는 없음), `CONTRACT_VER = 2`(정수) | B 에서 GET `/api/history` → 오늘 day 에 `{id: "hchk_tmp", s: "아이디어", t: "계약 확인용", item: "공통", phase: "grid1"}` → POST(base) → GET 에 `item` · `phase` 살아 있음 → 삭제 → POST |
| 3 | `dash_v2/results_newdata.py run()`: run 응답에 `phase: meta.get("phase")` 1줄 | `curl -s localhost:8890/api/result_blocks` 에 `phases` 사전과 `runs[판].phase`(1단계 판 = `grid1`, 나머지 null) |
| 4 | `js/history.js` 칸반 4열 + Quick Add(7-3 · 7-4), `js/main.js` · `js/core.js` 전역 필터(화재 · 배회·침입 · 쓰러짐) + `phase` · `item` 배지, `js/review.js` 그룹 이름표(블록 `label` + `phases` 이름표, 9절 문구) | 9절 규칙 위반 0. 은어 · 서술문 없음 |
| 5 | A 대시보드 재시작(먼저 `/api/sam2_jobs` 에 `running` · `queued` 없음 확인. pid 로 끄고 `dash_v2/` 에서 `../.venv/bin/python -u serve_kisa.py`, 로그는 `logs/dash/`) → B 로 `dash_v2/*.py` · `js/*.js` · `dashboard.html` 복사(`host.js` 제외) → B `dash.sh stop` → `dash.sh start` → `dash.sh status` | 두 서버 모두 `/api/history` 응답에 `readonly` 가 A true · B false |
| 6 | `ml_changelog.md` v1 · v2 항목 아래 `확인: 2026-MM-DD dash_v2 <커밋 7자>` 줄 + 머리 `미확인:` 정리 → `git add dash_v2 docs/dashboard.md ml_changelog.md` → `[dash]` 커밋 → `git pull --rebase` → 푸시 | `scripts/check_contract.py` 가 `CONTRACT_VER` 경고 없이 통과(ML 이 돌림) |
| 7 | ML 에 알림: "B 가 v2 서버. 34항목 `item` 소급 가능"(`ml_changelog.md` 요청 절 또는 채팅) | ML 이 B API 로 소급 → A 복사 · 커밋 |

검증 묶음(5 뒤):
```
# 서버 B
GET /api/history            # readonly false, HS_ST 에 아이디어
GET /api/result_blocks      # phases 5개, runs[*].phase
# 서버 A
GET /api/history            # readonly true
GET /api/sam2_jobs          # 재시작 전 running · queued 0
# 저장소
git status                  # dash_v2 · docs/dashboard.md · ml_changelog.md 밖 변경 0
grep -n "CONTRACT_VER" dash_v2/serve_kisa.py    # CONTRACT_VER = 2
```

그 다음부터: 4탭 다듬기(9절) · 요청 절 처리 · 새 계약 항목은 `ml_changelog.md` 가 알려 준다.

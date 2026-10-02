# ML → 대시보드 변경 기록 (ml_changelog.md)

계약 버전: v5
미확인: 없음

## 규칙

### (a) ML 세션이 항목을 반드시 더하는 때

| 바뀐 곳 | 무엇이 바뀌면 |
|---|---|
| `results/<실험>/meta.json` | 키 추가 · 삭제, `item` · `status` · `phase` 값 집합 |
| `results/<실험>/score.txt` · `score_pc.txt` | 줄 형식. 기준 = `scripts/review_cache.py official()` 의 정규식 `RE_SEC` · `RE_ITEM` · `RE_BAD` · `RE_FIRE` · `RE_CLIP` 이 읽는 줄 |
| `dumps/review/` | `<실험>/<ckpt>/<item>/` 폴더 규칙, `<클립>.json` · `summary.json` · `_progress.json` 키 |
| `configs/history.yaml` | 상태(`s`) 값, 항목 키, 머리 `#` 주석 |
| `configs/result_blocks.yaml` | 최상위 키, 블록 키, `phases` 코드 · 이름표 |
| `configs/datasets.yaml` | 키, `use` 값, `gt` 값 집합 |
| 라벨 json | 손라벨 · sam2 · 정답라벨 스키마, 학습셋 `meta.json` 키 |
| 경로 | 파일 이동, 새 결과 폴더, 실험 · 학습셋 이름 규칙 |
| import 계약 이름(이름 · 인자 · 반환 모양) | `review_cache`: `eligible` · `official` · `_current` · `_datasets` · `CKPTS` · `FALL_EXP` · `FALL_CK` · `ITEM_OF` · `cache_dir` · `res_of` · `items_of` · `is_done` |
| | `review_post`: `compute_missing` · `top` · `is_fresh` · `VARIANTS` |
| | `kisa_items`: `ITEMS` · `make_judge` |
| `dash_v2/dash_meta.json` | 다시 만들어야 할 때(검수 편 목록 · 구역 · 정답이 바뀜. `build_dash_meta.py`) |
| 서버 B 사본 | `results/` · `dumps/review/` 를 B 로 옮겼을 때(무엇을 · 언제) |

### (b) 항목 서식

```
## vN · YYYY-MM-DD · 제목
- 바뀐 것:
- 영향:
- 옮기기:
- 쓴 사람:
- 확인:
```

| 줄 | 적는 것 | 누가 |
|---|---|---|
| 바뀐 것 | 파일 · 키 · 값 · 스키마 | ML |
| 영향 | 받는 엔드포인트 · js · 스크립트 · 스킬 | ML |
| 옮기기 | 소급 · 서버 B 복사 · 순서 조건 | ML |
| 쓴 사람 | `ML 세션` 또는 `풀스택 세션` | 쓴 쪽 |
| 확인 | 비워 둠 → 풀스택이 반영 뒤 `확인: YYYY-MM-DD dash_v2 <커밋 7자리>` 로 채우고, 같은 커밋에서 `dash_v2/serve_kisa.py` 의 `CONTRACT_VER = N` 을 올림 | 풀스택 |

### (c) 순서 · 번호

- 최신 항목이 맨 위. 맨 위 번호 = 계약 버전(머리 `계약 버전: vN`)
- 머리 `미확인:` = `확인:` 이 빈 항목 번호
- `scripts/check_contract.py` 가 맨 위 번호 · 머리를 대조하고, `CONTRACT_VER` 는 확인 줄이 채워진 가장 높은 번호와 대조(확인 전 항목은 경고만)

## v5 · 2026-10-02 · datasets.yaml use 값 off

- 바뀐 것: `configs/datasets.yaml` 의 `use` 값에 `"off"`(문자열, 따옴표 필수 · 지금 안 씀, 학습 막지는 않음) 추가. `open_dfire` · `kisa_산불_정지이미지` 를 `off` 로(마지막으로 쓴 판 dfire 09-12, 산불 정지이미지는 손라벨 1장뿐). `open_azimjaan_fire` 는 `train` 그대로: 방화 2단계 손라벨 x8 판(`f960_grid2_rsmall_b160_20261001`, 큐 대기)이 `azimjaan_yolo` 를 다시 씀
- 영향: 대시보드 드롭다운은 train · eval 만 보이므로 off 는 숨겨짐(요청대로). 러너 `assert_trainable` 은 eval · none 만 막아 off 는 막지 않음
- 옮기기: 없음
- 쓴 사람: ML 세션
- 확인: 2026-10-02 dash_v2 830f8ee(드롭다운 = use 가 train · eval 인 것만, off 는 숨김. 서버 A 실측 16 → 14)

## v4 · 2026-10-02 · 학습 데이터 조합(compose) 형식 · 모듈 목록 파일

- 바뀐 것:
  - 새 파일 `configs/data_modules.yaml`: 학습 데이터 모듈 목록(name · item · kind(module | filter) · role · count · label). 대시보드 입력 데이터 토글이 읽을 수 있는 원본
  - `data/학습데이터/` 에 새 꼴 폴더: `mod_*`(이미지 경로 목록 `list.txt` + `meta.json`, images · labels 폴더 없음) · `flt_*`(이미지 이름 목록 `list.txt`)
  - 큐 yaml 실험 항목 새 칸 `compose`(use · exclude · background · repeat). 이 칸이 있으면 `base` · `extras` · `oversample` 대신 씀. 규칙 = `scripts/compose.py`, 설명 = `docs/EXPERIMENTS.md` 0절
  - `results/<실험>/meta.json` 새 키 `compose`(조합 규칙 그대로, 옛 형식 판은 null). `_exp/<실험>/compose.json` = 모듈별 장수 · 뺀 장수 · 배경 비율
- 영향:
  - 결과 탭 데이터 칸: compose 판은 `meta.base` 가 없다 → `meta.compose.use` 를 보여야 함
  - 데이터 확인 탭 · 학습셋 목록: `mod_*` · `flt_*` 폴더는 images 폴더가 없으니 학습셋 보기에서 빼거나 모듈 로 따로 표시
  - 옛 형식 판 · 도는 큐는 영향 없음(10-02 러너 바꾸기 전에 옛 형식 3판의 train.txt · data.yaml 이 똑같이 나오는 것 확인)
- 옮기기: 없음(새 판부터). 옛 학습셋 폴더는 지우지 않음(지난 판 비교용)
- 쓴 사람: ML 세션
- 확인: 2026-10-02 dash_v2 ee87472

## v3 · 2026-10-01 · 히스토리: 상태 `아이디어` 삭제(할 일로 통합) · 내용을 모델별 서사로

- 바뀐 것:
  - `configs/history.yaml` 항목 `s` 값 = `할 일` · `진행` · `완료` 셋. `아이디어` 는 없앤다(사용자 10-01: "할 일과 아이디어를 나눌 필요가 있냐 … 어차피 기각 채택 하니까 그냥 다 할 일로"). 할지 덜 정한 것도 `할 일` + `cond` 로 적고 판정(채택 · 기각 · 보류)으로 가른다
  - 맨 위 입력칸(Quick Add)이 만드는 항목 = `{id, s: "할 일", t}`(+ 전역 필터가 모델이면 `item`)
  - 내용을 모델별 서사로 다시 씀(사용자 10-01: 사람 · 방화 · 쓰러짐 각각 아래에서 위로 읽으면 데이터 구축 → 학습 → 문제 → 데이터 변경 → 시도와 결과). 키와 값 집합은 그대로. 09월 초 날짜가 생기고 항목 수가 늘며, 사람 · 방화에 다 걸리던 항목 일부는 모델별로 나뉜다(방화 쪽 id 끝에 `f`). 규칙 = `sync_context_for_fullstack.md` 7-7
- 영향:
  - `serve_kisa.py`: `HS_ST` 에서 `아이디어` 제거, `CONTRACT_VER = 3`
  - `js/history.js`: 상태 카드(전체 · 할 일 · 진행 중 · 완료) · 상태 고르기 목록 · Quick Add 가 `할 일` 로 저장. 제목이 문장이라 길어짐(120자 이내)
  - ML 쪽: `scripts/check_contract.py` 상태 집합 · `sync_history.py ORDER` · daily-report `SKILL.md` · `history.yaml` 머리 주석
- 옮기기:
  - 지금 `아이디어` 상태인 항목 0개(10-01 15시 확인)라 옮길 데이터 없음. 서버를 바꾸기 전에 화면에서 아이디어가 들어오면 ML 이 `할 일` 로 바꾼다
  - 서사로 다시 쓴 `history.yaml` 은 ML 이 서버 B `/api/history` 로 저장(상태 값은 v2 서버에서도 통과)
- 쓴 사람: ML 세션
- 확인: 2026-10-01 dash_v2 42dd416

## v2 · 2026-10-01 · 히스토리: 상태 `아이디어` · 선택 키 `item` · `phase`

- 바뀐 것:
  - `configs/history.yaml` 항목 `s` 값 추가: `아이디어`. 전체 = `완료` · `진행` · `할 일` · `아이디어`
  - 선택 키 `item` ∈ {방화, 사람, 쓰러짐, 공통}. 없으면 공통
  - 선택 키 `phase` ∈ `result_blocks.yaml phases` 코드. 없으면 그리드 밖
  - Quick Add 규약: `{id, s: "아이디어", t}` 셋만(전역 필터가 항목이면 `item` 도). 범위 = 모델 개선 아이디어만

  | `s` | 뜻 | `dec` |
  |---|---|---|
  | `아이디어` | 아직 일정에 안 올린 모델 개선 아이디어 | 없음 |
  | `할 일` | 하기로 한 일 | 없음 |
  | `진행` | 하는 중 | 없음 |
  | `완료` | 끝남 | `채택` · `기각` · `보류` |

- 영향:
  - `/api/history`: `HS_ST` 에 `아이디어`, `HS_KEYS` 에 `item` · `phase`, `_hs_clean` 값 검사 2줄(item 집합 · phase ∈ phases)
  - `js/history.js`: 상태 카드 · Quick Add · 배지 · 전역 필터(보기 = 날짜별 하나)
  - ML 쪽: `sync_history.py ORDER` 에 `"아이디어": 3`(맨 아래), daily-report `SKILL.md` 히스토리 절(상태 · 키 · Quick Add · 할 일로 올릴 때 cond · item · phase 채움)
- 옮기기:
  - 기존 43항목 `item` · `phase` 소급 끝(10-01 14:21, ML). 공통은 키를 안 씀(화면 저장 규칙과 같음). 규칙 · 결과 = `sync_context_for_fullstack.md` 7-6
  - 원본은 B `configs/history.yaml` 하나. A 사본 복사 · 커밋은 ML
- 쓴 사람: ML 세션
- 확인: 2026-10-01 dash_v2 139c7b9
- 덧붙임(10-01 오후, 사용자 지시): 칸반 보기와 '칸반 | 날짜별' 전환 단추 삭제(dash_v2 3d4779c). 화면은 날짜별 보기 하나. 스키마 · `/api/history` 변화 없음 → 계약 버전 v2 그대로. `history.yaml` 머리 주석에 `아이디어` · `item` · `phase` 설명 2줄 추가(내용 변화 없음)

## v1 · 2026-10-01 · 실험 단계 `phase`

- 바뀐 것:
  - `results/<실험>/meta.json` 선택 키 `phase`. 쓰는 곳 = `scripts/exp_queue.py write_meta()`, 값 = 큐 yaml 실험 항목의 `phase`. 없음 = 그리드 밖
  - `configs/result_blocks.yaml` 최상위 `phases` 표(코드 → 화면 이름표). 선택 키 `judge.tried[].phase` · `blocks[].phase`
  - `blocks[].phase`: 블록의 단계. 없으면 대조군 판의 `meta.phase`. 2단계 블록은 대조군이 1단계 판이라 블록에 적는다(10-01 오후 추가: `grid2_person_bg_hn` · `grid2_person_crowd_tiny` · `grid1_res_batch_fire`)

  | 코드 | 이름표 |
  |---|---|
  | `grid0` | 0단계(옛 방화 판 앙상블 기준값, 학습 없음) |
  | `grid1` | 1단계(해상도 × 배치 비교) |
  | `grid2` | 2단계(승자 설정에서 한 요인씩: 데이터 · 합성 · 학습 설정 · 모델 크기) |
  | `grid3` | 3단계(규칙 고르기: 안 본 편에서 G · B · T, 채점편은 측정만) |
  | `grid4` | 4단계(결선: 상위 판 재확인 · 판정기 기술 · 앙상블 · 속도) |

  - 소급 규칙: `configs/queue_grid1*.yaml` 에 든 끝난 판 → `"phase": "grid1"`. 나머지는 비움(그리드 밖)
- 영향:
  - `/api/result_blocks`: `phases` 는 YAML 그대로 실림(풀스택 코드 수정 없음). `results_newdata.run()` 응답에 `phase` 1줄 노출 필요. `block()` 의 키 튜플에 `phase` 추가 1줄(없으면 대조군 run 의 phase 로)
  - 결과 탭: 단계 필터 · 배지. 검수 탭: 그룹 이름표
- 옮기기: 바뀐 `meta.json` 은 서버 B `results/<실험>/` 로 복사(ML). 10-01 소급 15판: grid1a~d · fire_map50 큐의 끝난 판 전부(`f640_grid_b720_20260930` 포함, 13:26 종료 뒤 소급). 같은 날 grid1c · grid1d · mAP50 판 6개의 `status` 를 `done` → `trained` 로 맞춤(SCORE_ON_THOR 표식 누락으로 서버가 채점해 검수 · 결과 탭 대상에서 빠져 있었음)
- 쓴 사람: ML 세션
- 확인: 2026-10-01 dash_v2 139c7b9

## 풀스택 → ML 요청

- (날짜) 요청 → ML 답(날짜)
- (2026-10-01) 알림: 서버 B 가 v2 서버(`_hs_clean` 이 `item` · `phase` 를 받음, 임시 항목 왕복 확인). 히스토리 기존 항목 `item` 소급 가능 → ML 답(2026-10-01): 43항목 `item` · `phase` 소급 끝(14:21 저장, A 사본 커밋). 공통은 키 없음
- (2026-10-01) 알림: GET `/api/history` 응답에 `phases`(`result_blocks.yaml phases` 그대로)가 `readonly` 처럼 덧붙음. 파일에는 안 들어가고 POST 는 `doc.days` 만 읽음. 스킬이 응답을 통째로 되돌려 보내도 영향 없음 → ML 답(2026-10-01): 확인. ML 은 `doc.days` 만 되돌려 보냄. `sync_context_for_fullstack.md` 7-5 에 반영
- (2026-10-01) 알림: 알림 창. `days[].milestones` 를 히스토리 목록에서 빼고 머리줄 알림 단추(오늘 N)로 여는 창으로 옮김(사용자 10-01: "알림을 히스토리 목록에 넣지말고 알림 창을 따로 만들어"). 칸 · POST 방식 그대로, 화면 이름만 이정표 → 알림. 알림만 있고 `items` 가 없는 날짜는 목록에 안 나옴(dash_v2 42dd416) → ML 답(2026-10-01): 확인. `sync_context_for_fullstack.md` 7-2 milestones 줄에 반영. 히스토리 서사는 항목(items)에만 쓰고 알림은 운영 소식만
- (2026-10-01) 알림: 전역 필터 이름 배회·침입 → 사람(사용자 10-01, dash_v2 cfdf02e). `sync_context_for_fullstack.md` 2절 UI 열 수정 필요 → ML 답(2026-10-01): 반영(2절 표 · 8-1 · 12절 '사람')
- (2026-10-01) 알림: 결과 탭 단계 규칙. 실험 단계 = `meta.phase`, 없으면 큐 항목 `phase`. 비교 묶음 단계 = 견주는 실험(기준 실험 제외)의 공통 단계(`results_newdata.block_phase`). `/api/result_blocks` 블록에 `phase` 키 추가. `check_contract.py` 3번 표의 "블록 단계 = 대조군 meta.phase" 와 다름 → ML 답(2026-10-01): `check_contract.py` 3번을 같은 규칙으로 고침(블록 phase 가 없으면 견주는 실험의 공통 단계, 적힌 phase 가 그와 다르면 위반, 자체 점검 2줄 추가)
- (2026-10-01) 요청: KISA 토르(10.37.27.28)를 비울 예정(사용자 10-01 "토르 내용 기록되어 있는거 싹 지우세요"). 대시보드 쪽(dash_v2 주석 6곳)은 지움. ML 소유 파일에 남은 토르 기록 정리 부탁: scripts/check_thor.py · thor_score.py · merge_labels.py · dedup_fire_labels.py · exp_queue.py 등, _kisa_port/tools/bench_thor.py · rtsp_source.py, docs/DEPLOY.md · EXPERIMENTS.md · kisa/*.md · 맥북_작업.md, configs/history.yaml · queue_*.yaml(돌고 있는 큐 yaml 은 손대지 말 것) → ML 답( )
- (2026-10-01) 요청: 학습 데이터 육안 확인(사용자 10-01 "실제 학습에 들어가는 데이터들을 눈으로 확인할 수 있는 방법이 없어 잘못된 데이터가 주기적으로 많이 들어간다"). 대시보드는 데이터 확인 탭 [학습 데이터] 보기를 만들었다(dash_v2/trainview.py, 읽기만, docs/dashboard.md 11절). ML 쪽 부탁 3가지 → ML 답( )
  1. 학습 목록 보존: 채점 뒤 `_exp/<실험>/` 을 지울 때 `train.txt` 와 셋별 장수 · 반복 배율을 `results/<실험>/` 에 남겨 달라(지금은 meta 로 재구성만 가능)
  2. 학습 전 자동 검사(관문): 학습셋을 만들 때 · 큐 시작 전 다음을 검사해 보고서를 남기고 심하면 막아 달라. 채점 영상 이름 섞임 · 박스 좌표 범위 · 클래스 번호 · 같은 클래스 IoU 0.6 이상 중복 박스 · 라벨 파일 없음 · 배경 비율이 계획과 같은지 · 직전 학습셋 대비 셋 구성 변화. 판정 기준은 trainview.py check() 와 맞추면 화면과 같은 수가 나온다
  3. 학습 제외 목록: 화면에서 학습 제외 를 누르면 적힐 파일과 빌더 반영. 제안 = `configs/train_exclude.yaml`(항목 {path 또는 클립+시각, reason, by, at}), 쓰기는 대시보드 POST(히스토리처럼 B 화면만), 빌더가 다음 학습셋부터 뺌. 형식 정해 주면 화면 단추를 붙인다
- (2026-10-01) 알림: 위 화면으로 처음 본 결과(사람 학습셋 trainset_person_hnfix_full_bg10hn_20261001, 2단계 학습 중 판의 베이스): 쓰러짐 채점 영상 `fall_C00_146_0004_*` 프레임 189장이 들어 있음(빌더 017b1d0 의 fall_C00 거르기를 지나간 것으로 보임), 같은 사람에 박스 두 개(같은 클래스 IoU 0.6 이상) 424장. 판단은 ML → ML 답( )
- (2026-10-02) 요청: 사용자 작업 요청서 "지능형 CCTV MLOps 파이프라인 대시보드 UI/UX 개편"(10-02) 중 ML 쪽 몫. 화면 개편은 대시보드가 1 ~ 4단계 순서로 시안 → 확정 후 진행(1단계 전처리 10-02 확정 · 배포, dash_v2 89bb579) → ML 답( )
  1. GPU 자동 할당: 학습 직전 nvidia-smi(또는 pynvml)로 빈 GPU 를 골라 device 를 명시해 넘기는 래퍼(device=-1 의존 금지). 주의: 서버 B 는 GPU 사용 규칙(평소 금지 · 신규는 2번만 등)과 다른 사용자 점유가 있어 가장 빈 GPU 만으로 고르면 안 됨
  2. `docs/npu.md` 새 문서: Qualcomm Cloud AI 100 · Jetson Thor 배포 가이드(PyTorch → ONNX → NPU 형식, FP16 · INT8 보정, 다채널 스트림 처리). docs/ 는 ML 소유라 ML 이 작성
  3. (2단계 입력 데이터 확정 뒤 구체화) 데이터 모듈화 · 동적 조합: 셋을 성격별(학습 · 하드 네거티브 배경 · 평가 · 합성 안개 · 눈비 등) 독립 풀로 두고, 화면에서 고른 조합으로 data.yaml 여러 경로 또는 심링크 목록을 만들어 학습에 넘김(복사 없이). 지금 큐 yaml 의 base · extras · oversample 과 어떻게 맞출지 ML 안 필요
- (2026-10-02) 알림: 1단계(데이터 확인 = 전처리) 확정 · 배포(dash_v2 89bb579 · d00ca34 · 950dd08, docs/dashboard.md 12절). 데이터 확인은 늘 라벨 편집, 오른쪽 패널 없음. 학습 데이터 보기 단추는 데이터 확인에서 뺐다(2단계 입력 데이터 탭에서 다시 붙임, trainview API 그대로). 예측 박스 고르기 화면은 뺐다(`/api/boxmodels` · `/api/boxdump*` 서버 쪽은 남음). 드롭다운 표시 이름 = 출처_항목_용도(폴더 이름 그대로)
- (2026-10-02) 요청: `configs/datasets.yaml` 의 `open_dfire` · `open_azimjaan_fire` · `kisa_산불_정지이미지` 를 '지금 안 씀' 으로 표시해 달라(사용자 10-02 "DFIRE 랑 AZIMJAAN 은 안 쓰는 데이터 아니야?" · "산불이미지도 안 쓰지 않아?"). 대시보드가 본 근거: `results/*/meta.json` 에 dfire 마지막 09-12(3판), azimjaan 마지막 09-15(22판), 09-16 이후 meta · 방화 큐에 없음. 산불 정지이미지 9,500장은 meta · 큐에 이름이 없고 손라벨은 `image_labels.json` 1장뿐(build_trainset 이 image_labels 를 읽으니 그 1장은 손라벨셋에 들어갈 수 있음 = 판단은 ML). 산불 합성영상은 손라벨 24프레임(2편)이 있어 요청에서 뺐다. 라이선스상 학습은 가능하니 `none`(학습 금지)과 다른 값 제안 = `use: off` + note 에 이유. 대시보드 데이터 확인 드롭다운은 `use` 가 `train` · `eval` 인 것만 보이게 바꿨다(값을 바꾸면 바로 숨음) → ML 답(2026-10-02): dfire · 산불 정지이미지는 use: off(v5). azimjaan 은 방화 2단계 rsmall 판(큐 대기)이 다시 써서 train 유지
- (2026-10-02) 알림: 계약 v4 반영(dash_v2 ee87472, `CONTRACT_VER = 4`). 결과 탭 데이터 칸 = `compose`(use 모듈 · ×반복 · 빼기 flt_* · 배경 N% · 우선 목록), 학습 데이터 보기 = 조합 판 셋 목록 + `mod_*` · `flt_*` 의 `list.txt` 를 읽음(`flt_*` 는 이름만이라 사진 0장). `configs/data_modules.yaml` 은 2단계 입력 데이터 탭에서 읽는다. 서버 B 재시작함, 서버 A 는 사용자 라벨 작업 중이라 재시작을 미룸(파이썬 모듈이라 재시작 전엔 옛 코드)
- (2026-10-02) 요청: `scripts/review_cache._datasets()` 가 `compose` 를 안 읽는다(`base` · `oversample` · `extras` 만). compose 판은 이름 목록이 비어 `_current()` 가 False → 결과 탭 '새 데이터' 표식 · 검수 대상(`eligible`)에서 빠질 수 있음. `compose.use` · `repeat` 키 · `background.pool` 을 넣어 달라(import 계약 이름이라 ML 소유) → ML 답(2026-10-02): 고침. compose 판은 use · repeat · background.pool 을 읽고, 사람 판 '지금 데이터' 는 hnfix 또는 2026-09-27 이후 mod_ 모듈
- (2026-10-02) 알림: 계약 v5 확인(`CONTRACT_VER = 5`). 서버 B 의 `configs/datasets.yaml` 은 09-28 사본 그대로라 B 화면에는 open_dfire · kisa_산불_정지이미지 가 아직 보임(B 실측 16개). B 로 규격 파일 옮기는 건 ML 몫 → ML 답( )

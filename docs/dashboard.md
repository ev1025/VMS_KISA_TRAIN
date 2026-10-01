# 라벨 대시보드 (dash_v2) 구조 및 운영 가이드
> **기준일:** 2026-09-11 (DINO 초안/자동감지 기능 제거 반영)
> **환경:** 서버 `dash_v2/serve_kisa.py` (포트 8890) / 클라이언트 `dash_v2/js/*.js`

---

## 1. 데이터 규격 및 클래스 규칙 (하드코딩 금지)
모든 데이터셋 규격은 단일 기준 파일인 **`configs/datasets.yaml`**에서 제어합니다. 새로운 데이터셋 추가 시 코드 수정 없이 yaml만 수정합니다.

* **포맷 어댑터:** `dash_v2/gt_adapters.py`를 통해 원본 정답(yolo, coco, voc, kisa_xml 등)을 공통 규격으로 변환합니다.
* **고정 클래스 규약:**
  * `fire` 모드: **0** (불), **1** (연기)
  * `person` 모드: **0** (사람)
  * ※ 원본 클래스가 다를 경우 yaml의 `classes` 속성으로 매핑하거나 버립니다.
* **학습 데이터 사용 여부 (`use` 속성):**
  * `eval`: 채점 전용 (학습셋 빌더가 제외하도록 라벨에 `eval: true` 부착)
  * `none`: 라이선스 문제 등으로 학습 금지 (읽기 전용)
* **학습셋 빌드 우선순위:** **손라벨 ➔ SAM 전파 ➔ 원본 정답(GT)** 순으로 병합됩니다. (`scripts/build_trainset.py` 사용)

---

## 2. 라벨 저장소 및 병합 규칙
데이터는 3개의 저장소로 분리되어 관리되며, 화면 표시 및 학습 시 우선순위가 존재합니다.

| 저장소 | 파일 경로 | 생성 주체 | 특징 및 규칙 |
| :--- | :--- | :--- | :--- |
| **1. 손라벨** | `data/학습데이터/손라벨/*_labels.json` | 편집기 직접 저장 | 최우선 적용. 이 박스가 있는 프레임은 SAM 전파 결과를 덮어씁니다. |
| **2. SAM 전파** | `data/학습데이터/자동라벨/sam2/<stem>.json` | 전파 큐 워커 | 손라벨이 없는 프레임을 채웁니다. 바로 학습에 사용 가능합니다. |
| **3. 원본정답** | `data/학습데이터/정답라벨/<stem>.json` | 가져오기 스크립트 | 읽기 전용. 클릭하여 수정하면 **손라벨**로 승격되어 저장됩니다. |

* **프레임 격자(Grid):** 사람 클립은 0.5초(2FPS), 화재 클립은 1초 간격으로 처리합니다.
* **검토완료 마커(`cls -1`):** 원본 정답(초안) 표시를 막는 역할을 하며, SAM 전파 결과는 막지 않습니다.

---

## 3. 화면 및 편집기 조작 규칙

### 3.1 화면 공용 로직 (중복 구현 금지)
* **영상:** `renderCenter(row)` 단일 함수로 렌더링. 
* **이미지:** 중앙 `img` 태그 및 SVG 박스 오버레이로 렌더링 (세로 중앙 정렬).
* **레이아웃:** 좌측(태그 배지), 우측(상세 정보 KV 카드).

### 3.2 객체 및 참조샷 규칙
* **객체 번호 고정:** 박스의 객체 번호(`obj`)는 고정 속성입니다. 위치/크기를 변경해도 거리를 계산해 번호를 추정하지 않습니다.
* **화재 객체 단축키:** `1` (불, cls 0), `2` (연기, cls 1). 
* **참조샷 생성 조건:** 탭(SAM 점 찍기), 빈 곳 드래그(새 박스 생성), `C`키(이전 프레임 복사). ※ 단, **연기**는 참조샷을 만들지 않습니다.
* **박스 이동:** 전파된 박스를 사용자가 이동하면 **손라벨**로 고정되며, 참조샷은 새로 생성되지 않습니다.
* **제외점(Negative Point):** 제외점 클릭만으로는 SAM 모델을 호출하지 않습니다.

### 3.3 편집기 API 매핑

| 기능 | 클라이언트 액션 | 서버 엔드포인트 | 비고 |
| :--- | :--- | :--- | :--- |
| **SAM 점/박스 적용** | `samPoint` ➔ `applyMask` | `POST /api/sam2_mask` | SAM2 이미지 모델 (코어) |
| **손라벨 저장** | `saveNow` ➔ `postLabel` | `POST /api/savelabel` | 해당 프레임의 기존 SAM 결과 제거 |
| **구간 전파** | `bGo` | `POST /api/sam2_propagate_start` | 참조샷 기반 전체/구간 큐 워커 실행 |
| **이어서 전파(교정)**| `refineWindow` (구간 좁힘) | 위와 동일 (파라미터 차이) | 직전~직후 참조샷 구간만 객체 단위 병합 |
| **전파 지우기** | `bClr` | `POST /api/sam2_clear` | 기존 전파 결과 삭제 (참조샷은 유지) |

---

## 4. SAM2 전파 모드 설정
기본 설정은 `configs`의 `PROP_DEFAULT_MODE`를 따릅니다.

* **기본값 (`separate`):** 객체마다 독립된 세션과 임계값을 가집니다. 불과 연기가 하나의 마스크로 뭉개지는 것을 방지합니다.
* **전파 범위:** 참조샷 사이의 세그먼트 단위로 새로운 세션을 생성하여 전파합니다. 연기의 경우, 하나의 참조샷만으로는 형태를 오래 추적하기 어려우므로 잦은 참조샷 생성과 **'이어서 전파(교정)'** 워크플로우를 권장합니다.

---

## 5. 서버 운영 및 주의사항
* **서버 재시작:** 큐가 메모리 상에 존재하므로, 진행 중인 전파 작업이 없을 때(`/api/sam2_jobs` 확인) 재시작해야 합니다.
* **프로세스 종료:** `kill`과 `start`는 분리된 SSH 세션/명령으로 실행하세요. (`pkill -f` 사용 시 자기 자신을 종료할 위험이 있습니다.)
---

## 6. 영상 검수 탭 (2026-09-28 재설계)
검수 탭은 **미리 계산한 결과만 읽는다**. 모델을 눌러도 추론하지 않는다.

| 무엇 | 어디 | 규칙 |
| :--- | :--- | :--- |
| 대상 판 고르기 | `scripts/review_cache.py` `eligible()` | '지금 데이터'로 COCO 사전학습부터 학습해 끝난 판만. 사람 = 학습 데이터 이름이 전부 `hnfix` 계열, 방화 = KISA 쪽 데이터가 전부 09-26 방화 라벨 이후. 이어 학습·배포 가중치·도는 판 제외 |
| 계산 | `scripts/review_cache.py` (tmux `reviewcache`, 로그 `logs/review_cache.log`) | `_kisa_port/tools/kisa_items.py` 의 검출기·추적기·규칙을 그대로 불러 영상 끝까지. 규칙에는 경보 확정 전까지만 먹인다(채점과 같은 경보). best 를 모든 판에서 먼저, 배회를 침입보다 먼저 |
| 저장 | `dumps/review/<실험>/<best\|last>/<fire\|intrusion\|loitering>/` | 편마다 `<클립>.json`(표본별 박스·신호·구역·경보·판정), 다 끝나면 `summary.json`. 계산 중엔 `_progress.json` |
| 화면 API | `/api/review_models?item=` · `/api/review_summary?key=&item=` · `/api/review_clip?key=&item=&clip=` | 읽기 전용. `key` = `<실험>\|<best\|last>` |
| 작업 PC 채점 대조 | `review_cache.official()` 이 `results/<실험>/score.txt` 를 읽는다 | 목록 점수 옆에 작업 PC 점수, 편 판정이 다르면 오른쪽에 '작업 PC: …' 표시 |

* 목록 판정·재생바 신호·예측 경보·박스가 모두 고른 모델 하나에서 나온다. 모델이 없으면 정답과 구역만 보인다.
* 예전 검수 탭이 쓰던 `dash_meta.json` 의 `signal`·`sa`·`tracks`(배포 모델 값)와 `js/core.js` 의 JS 판정 함수(옛 규칙 상수)는 검수 탭에서 더 쓰지 않는다. JS 판정 함수는 지웠다.
* 데이터 확인 탭의 '예측 박스' 고르기(`/api/boxmodels` · `/api/boxdump*`, 누르면 추론)는 예전 그대로다.

* 2026-09-29 바뀜: 새 판의 검수 저장은 작업 PC 채점 감시가 **채점과 한 번에** 만든다(영상 끝까지 한 번 돌려 그 결과로 채점 로그 · SA 와 `dumps/review` 를 같이 씀. 작업 PC `pc_review.py`). 대조: 작업 PC 로 낸 편별 판정 = 채점기 판정. 서버 A 루프(tmux `reviewcache`)는 껐다. 서버 A 가 만들었던 배회(장비 차이 2편)는 작업 PC 가 다시 만들어 덮는다. `summary.json` 의 `where` 가 계산 장비다.

---

## 7. 결과 탭 (2026-09-29 재설계)
옛 결과 탭(모든 판 · 서버 채점 · 규칙 스윕 · 클립 히트맵)을 뺐다. 결과 탭은 **새 데이터 실험만, 비교 블록으로** 보인다.

| 무엇 | 어디 | 규칙 |
| :--- | :--- | :--- |
| 블록 정의 | `configs/result_blocks.yaml` | 사람이 정하는 것만: 질문 · 독립변수(iv) · 실험마다 달라도 되는 설정(vary) · 대조군 · 실험별 조건 · 결론, 항목별 종속변수(dv) · 판정 기준(rule) · 용어 정리(terms). 점수 · 인자 · 장수는 옮겨 적지 않는다 |
| 계산 | `dash_v2/results_newdata.py` (`/api/result_blocks`) | 점수 = `review_cache.official()`(사람 `score.txt` · 방화 `score_pc.txt`), 학습 인자 = `runs/<판>/<모델>/args.yaml`(학습 전이면 큐 yaml), optimizer = 러너 로그에서 실제로 고른 것, 검증셋 = `_exp/<판>/data.yaml` 의 val 파일 내용 |
| 통제변수 · 독립변수 | 같은 파일 `block()` | 블록 안 모든 실험의 인자를 견줘 같으면 통제변수, 다르면 독립변수. vary 밖 설정이 다르면 '교란 변수' 경고. patience 가 달라도 모든 실험이 계획 에폭을 끝까지 돌았으면 '차이(영향 없음)' |
| 판정 | 같은 파일 `verdict()` | 항목마다 best · last 중 F1 낮은 쪽(같으면 last)의 정검 수로 대조군과 견준다. 합이 2편 미만 차이면 동률 |
| 진행 · 예상 종료 | 화면이 `/api/queue` 를 같이 읽음 | 상태 칸 = 채점 완료 · 채점 대기 · 에폭 진행 · 대기. 날짜는 '학습 종료' 칸(학습 중이면 러너의 예상 시각) |

* 블록에 없는 새 데이터 실험(끝난 것 · 학습 중인 것)은 맨 아래 '블록에 없는 새 데이터 실험' 표에 저절로 나온다. 실험을 새로 걸면 `result_blocks.yaml` 에 블록을 더한다(서버 재시작 필요 없음, 코드 수정 때만 재시작).
* `review_cache.official()` 은 09-29 부터 방화 `score_pc.txt` 도 읽는다(검수 탭의 작업 PC 대조도 방화가 같이 나온다).
* 맨 위 '용어 정리'(접힘)는 `result_blocks.yaml` 의 `terms` 에서 그린다. 실험 이름 · 데이터 이름 용어가 새로 생기면 거기에 한 줄 더한다.
* 옛 `/api/results` 는 서버에 남아 있으나 화면에서 더 부르지 않는다.
* 맨 위 = 옛 결과 탭과 같은 큐 상자(실행 중 실험 · 에폭 · 이 에폭 · 속도 · 에폭당 · 예상 종료 · 최근 mAP · GPU + 러너 로그, 30초 갱신). 그 위 요약 줄은 뺐다
* 사본 서버(서버 B 등, 2026-09-29): `results/` · `dumps/review/` · 끝난 새 데이터 판의 `runs/<실험>/<모델>/`(args.yaml · results.csv · weights/best · last) 를 옮기면 검수 · 결과 탭이 뜬다. meta 의 절대 경로는 `review_cache.local_path()` 가 저장소 기준으로 바꾸고, 결과 탭은 학습 서버가 적어 둔 `results/<실험>/run_info.json`(학습 인자 · 검증셋 · 돈 에폭) 을 읽는다
* 이 데이터는 git 에 넣지 않는다: 검수 파일에 KISA 영역 다각형 · 정답 시각이 들어 있고 점수 파일에도 편별 정답 시각이 있다(진흥원 자료에서 나온 것). 새 판이 끝나면 학습 서버 → 사본 서버로 직접 옮긴다

---

## 8. 계약 v1 · v2 반영 (2026-10-01)
계약 원문 = 루트 `sync_context_for_fullstack.md` · `ml_changelog.md`. `serve_kisa.py` 의 `CONTRACT_VER` = 반영한 계약 버전.

| 무엇 | 어디 | 규칙 |
| :--- | :--- | :--- |
| 전역 항목 필터 | `js/core.js` `GF_DEF` · `GF`, 단추 = `js/main.js buildMode()` | 전체 · 화재 · 배회·침입 · 쓰러짐. 모든 탭에 적용, `localStorage kisa_gf` 에 기억. 계층별 이름(meta.item · 검수 item · 점수 카드 · 라벨 모드)은 `GF_DEF` 한 곳 |
| 데이터 확인 탭 | `js/data.js buildDatasetSrc()` | 원본 목록을 라벨 모드로 거름. 여러 항목이 섞인 배포 검증영상은 늘 보임 |
| 영상 검수 탭 | `js/review.js buildSrc()` · `serve_kisa.py review_models()` | 검수 항목 = 필터 안에서만. 그룹 이름표 = 블록 `[날짜] 제목` + 대조군 `meta.phase` 의 `phases` 이름표 |
| 결과 탭 | `js/main.js nrDraw()` · `results_newdata.run()` | 점수 카드 · 블록 · 블록 밖 실험을 필터로 거름. 실험마다 모델 · 단계 배지, 단계 고르기(`localStorage nr_ph`). `runs[판].phase` = `meta.phase` |
| 히스토리 탭 | `js/history.js` · `serve_kisa.py _hs_clean()` | 칸반 4열(아이디어 → 할 일 → 진행 → 완료), 카드 끌어 옮기기 = 상태 변경(완료 밖으로 가면 판정 지움), 맨 위 Quick Add = `{id, s: 아이디어, t}`(+ 필터 항목이면 `item`). `item` · `phase` 배지, 날짜별 보기는 단추로 전환(`localStorage hs_view`) |
| 히스토리 검증 | `_hs_clean()` | `item` ∈ 방화 · 사람 · 쓰러짐 · 공통(없으면 공통), `phase` ∈ `result_blocks.yaml phases` 코드 |
| 단계 이름표 | GET `/api/history` 응답 `phases`, `/api/result_blocks` 응답 `phases` | `configs/result_blocks.yaml phases` 값 그대로. 응답에만 실리고 `history.yaml` 에는 안 들어감 |

* 배포: 서버 A 는 `dash_v2/` 에서 pid 로 끄고 `nohup ../.venv/bin/python -u serve_kisa.py >> ../logs/dash/serve_kisa.log 2>&1 < /dev/null &`, 서버 B 는 파일 복사(`js/host.js` 제외) 뒤 `./dash.sh stop` · `./dash.sh start` 따로. 둘 다 `/api/sam2_jobs` 가 빈 것을 먼저 확인.
* 확인: 서버 B 에서 임시 항목(`item` · `phase` 포함) 저장 → 다시 읽기 → 삭제. 서버 A `/api/history` 는 `readonly: true`.

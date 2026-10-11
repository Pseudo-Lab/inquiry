# M3 Saturation / Dedup (Heuristic MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `executing-plans` / `test-driven-development` / `verification-before-completion`. 체크박스는 검증 후에만 완료로 바꾼다.

**Goal:** MILESTONES §M3의 "사고 포화·중복 감지(§8)"를 **단순 휴리스틱 MVP**로 구현한다. (1) 의미 중복 가설 near-duplicate 감지, (2) 사고 포화 신호(새 가설·근거·연결·상태변화가 없는 반복). **삭제·자동병합 없음 — 감지·플래그·신호만.** MILESTONES 지침: "단순 휴리스틱으로 시작, 임베딩은 점진, 여기서 완벽 노리지 말 것."

**Architecture:** 읽기 전용 분석. `src/inquiry/saturation.py`(weekly.py와 같은 레벨)에 순수 함수로 유사도·중복 탐지·포화 계산을 둔다. 포화는 **이벤트 로그만으로** 계산(replay 불필요, weekly.py 윈도우 패턴 재사용). near-duplicate는 `title+claim` 토큰 Jaccard. 상태/이벤트를 바꾸지 않으므로 저위험(detection + advisory).

**Tech Stack:** Python 3.9+, 표준 라이브러리 unittest. 새 의존성 없음(임베딩/외부 NLP 라이브러리 사용 안 함 — v0 휴리스틱).

**Status:** 2026-10-12 계획 수립 → critic 1회차 CHANGES NEEDED → B1·B2·G1·G2 반영해 개정 → **Task 1~4 구현·검증 완료(2026-10-12).** 신규 20 테스트, 전체 141 그린.

**선행 결정 (휴리스틱 v0, 전부 tunable·후속 정교화):**
- **유사도 = 정규화 토큰 Jaccard(title+claim).** 정규화 `' '.join(text.split()).casefold()`(기존 branch/operation 패턴과 동일). 임베딩은 후속.
- **near-dup 기본 임계 0.5**(Jaccard). CLI `--threshold`로 조정. 짧은 claim·한국어(조사로 토큰 불일치)에서 재현율 낮을 수 있음을 전제(ADR에 명시).
- **중복 탐지 범위 = active 가설**(suggested/exploring/supported/contested = BRANCH_PARENT_STATES). 종료/통합은 제외.
- **(critic B1·B2) 포화 윈도우 = seq 구간.** 로그에서 `operation.startswith('hypothesis.')`인 `RunStarted`들을 agent run 경계로 삼아(= framing run 제외), **최근 N(기본 3)번째 RunStarted의 seq부터 끝까지**를 윈도우로 한다. 그 seq 구간의 **모든 이벤트**(agent run change + `human:local` accept/evidence 등 포함)에서 net-new change를 센다 — net-new 가설 생성은 accept(human) 이벤트에서 나오므로 run change만 세면 항상 0으로 오탐.
- **net-new kinds:** HypothesisCreated·EvidenceCreated·EvidenceLinked·HypothesisStateChanged·ConfidenceUpdated. (`HypothesisAssessed`는 기존 노드의 초기 추정이라 새 탐구 정보로 보지 않아 제외.) 삭제 이벤트가 없으므로 "Created 수 = net-new"가 성립.
- **포화 판정:** `saturated = (윈도우 내 hypothesis.* RunStarted 수 >= window) and (net-new == 0)`. run이 부족하면 saturated=False(데이터 부족).
- **감지·플래그만.** 자동 삭제·병합·상태변경 없음. §8의 "보류/관점변경/종료 제안"은 신호 노출로 그친다(행동은 사람).
- **novelty 축 연계는 후속.** v0 dedup은 텍스트 유사도. D3 novelty 점수와의 결합은 후속.
- **weekly는 패턴 참고(코드 공유 아님).** weekly는 시간축, saturation은 run수(seq)축이라 다름. 재사용 import 없음.

## Global Constraints

- 정본: [MILESTONES §M3](../../MILESTONES.md), [PRODUCT-CONCEPT §8·§20](../../PRODUCT-CONCEPT.md), [ADR-D3](../../decisions/ADR-D3-confidence-model.md)(novelty).
- **읽기 전용.** 이벤트를 쓰지 않는다. 상태 projection을 바꾸지 않는다. 순수 함수 + CLI 조회 + proposal view advisory 필드만.
- **포화는 이벤트 로그로 계산**(`Store.read_all()`), replay 불필요. weekly.py의 윈도우 필터 패턴 재사용.
- **기존 정규화/중복 로직 비파괴.** branch/operation의 기존 candidate 중복 검사는 그대로. saturation.py에 자체 `normalize_text`를 두고, 기존 코드 리팩터링(통합)은 **선택적 후속**(회귀 위험 회피).
- **novelty·assessment 미변경.** D3 스키마를 건드리지 않는다.
- `.env`·실제 `.inquiry`·사용자 환경 미수정. 테스트는 합성 데이터+TemporaryDirectory.
- 구현 순서 Task 1→2→3→4. 각 단계 통과 전 다음으로 확장 금지.

## 파일과 책임

| 파일 | 책임 |
|---|---|
| 새 `saturation.py` | `normalize_text`·`similarity(a,b)`·`find_near_duplicates(state, threshold)`·`compute_saturation(events, window)`·`build_report(events, state, ...)`. 순수 |
| 수정 `features/branch/service.py` | `_view`에 `near_duplicates`(candidate claim vs active 가설) advisory 필드 |
| 수정 `ui/cli.py` | `inquiry saturation [--window N] [--threshold T]` 조회 명령(JSON report) |
| 새 `docs/decisions/ADR-D11-saturation-dedup.md` + README | 휴리스틱 v0·flag-not-delete·임계 tunable 결정 |

## Tasks

### Task 1 — `saturation.py` 순수 휴리스틱
- `normalize_text(s)`, `similarity(a, b)`(정규화 토큰 Jaccard), `find_near_duplicates(state, threshold=0.5)`(active 가설 쌍 중 임계 이상 → `[{a, b, score}]`), `compute_saturation(events, window=3)`(seq 구간: 최근 N번째 `hypothesis.*` RunStarted부터 끝까지, 그 구간 모든 이벤트의 net-new 카운트 → `{saturated, runs_in_window, new_info, window, reasons}`), `build_report(events, state, window, threshold)`.
- **수용 기준:** 동일/유사 claim 쌍 감지, 무관 쌍 미감지, 임계 경계 동작. active만 비교. **포화: hypothesis.* run N회가 net-new 0이면 saturated; accept(human)로 새 가설 생기면 not saturated(net-new가 human 이벤트에서 집계됨을 검증); framing run은 run 카운트에서 제외; run 부족 시 saturated False.** 빈 로그 edge case. 순수 함수 테스트.

### Task 2 — branch proposal view near-duplicate advisory
- `features/branch/service._view`에 `near_duplicates` 추가 — 각 candidate(`title+claim`)를 **부모(`proposal['parent_id']`)를 제외한** active 가설과 비교해 임계 이상이면 `[{candidate_id, similar_hypothesis_id, score}]`.
- **수용 기준:** 기존 가설과 유사한 candidate가 플래그됨. **부모와의 유사도는 플래그 안 함**(fork는 부모 파생). candidate는 `title+claim`으로 비교(similarity와 일관). 무관하면 빈 목록. 기존 `stale`/`agent` 무회귀.

### Task 3 — CLI `saturation`
- `ui/cli.py`: `inquiry saturation [--window N] [--threshold T]` → `build_report` JSON(saturated 신호 + near-duplicate 목록). 키 불필요. weekly/show와 동일 dispatch 패턴(`Store.read_all()`+`replay`).
- **수용 기준:** report에 saturation 신호와 중복 목록 포함. `--window`/`--threshold` 반영. 키 없이 조회. **inquiry 미초기화/빈 로그 시 에러 없이 데이터 부족 신호**(saturated False, duplicates []).

### Task 4 — ADR-D11 + 문서
- ADR-D11(휴리스틱 v0·flag-not-delete·임계 tunable·임베딩/novelty 연계 후속) + README 등록.
- **수용 기준:** ADR이 코드 동작과 정합. 열린 질문(임계 실측·임베딩·novelty 연계·자동 synthesis 유도) 명시.

## 범위 밖 (후속)
- **임베딩 기반 의미 유사도**(현재 토큰 Jaccard). 
- **novelty 축(D3)과 dedup 결합** — 낮은 novelty를 중복 신호로 연계.
- **자동 synthesis/archive 유도**(§20) — 감지 후 사람이 행동, 자동화는 후속.
- **operation proposal view 중복 플래그**(이번엔 branch만).
- **정규화 헬퍼 통합 리팩터링**(branch/operation과 공유) — 회귀 위험 회피, 선택적 후속.
- **포화 시 자동 보류/종료** — 신호만, 행동은 사람.

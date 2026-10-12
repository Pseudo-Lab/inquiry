# B2 — NOW / NEXT / LATER 뷰 (plan)

> 핸드오프 Track B/B2. 시간축을 NOW/NEXT/LATER로 표현. **§20 경고 준수**: 캘린더/스프린트/마감 아님 —
> 가설 상태에서 파생되는 "주의 지평(attention horizon)" 렌즈. review/status와 동일한 순수-투영 패턴.

## 1. 목표 / 범위
- **목표:** 열린 Action과 주의가 필요한 가설을 NOW/NEXT/LATER로 그룹한 뷰(CLI `plan` — JSON + text).
- **범위 밖:** 날짜/마감/우선순위 숫자, TUI 패널(후속), 새 이벤트(순수 read-only).

## 2. 현황 (코드 근거)
- `Action`(model.py): `id, hypothesis_id, title, done, created_at, done_at`. **우선순위/마감 필드 없음**(과확장 금지와 합치).
- `monitor.review(events, state)`(monitor.py:147): 상태별 그룹({triage,decide,resolve}) + suggested_actions. 순수 함수.
- `monitor.summary`/`review` → CLI `status`/`review`가 JSON 출력(cli.py:223-226, 474-489). text 렌더는 review는 JSON 전용(피벗).
- 상태 집합(transitions): suggested/exploring/supported/contested/suspended/refuted/human-closed/synthesized.

## 3. 접근
`monitor.plan(state)` 순수 함수 + `render_plan_text(plan)` + CLI `plan`(JSON 기본, `--text` 사람용).

### 3.1 분류 규칙 (상태 파생, 날짜 무관) — critic gap1/2 교정: 완전한 매핑, 조용한 누락 없음
**status→bucket 매핑**(모든 비종결 상태를 덮음):
- **NOW**: `exploring`, `contested`
- **NEXT**: `suggested`, `supported`
- **LATER**: `suspended`
- **제외(종결)**: `refuted`, `human-closed`, `synthesized` — 가설도 그 action도 어느 버킷에도 없음.

**각 비종결 가설**은 반드시 한 버킷에 나타난다:
- 열린 Action이 1개 이상이면 → 그 **Action들**을 `bucket[status]`에(가설 자체는 중복 추가 안 함).
- 열린 Action이 0개면 → **가설 자체**를 `bucket[status]`에(hypothesis 항목).
- ⇒ exploring/supported가 action이 없어도 각각 NOW/NEXT에 가설 레벨로 노출(조용한 누락 없음, critic gap1/2).
- 종결 가설의 열린 Action도 제외(종결된 가설의 잔여 action은 actionable 아님).

### 3.2 항목 셰이프
`{kind: 'action'|'hypothesis', id, hypothesis_id, title, status}`
- action: id=A-ID, title=action.title, hypothesis_id/status=소속 가설.
- hypothesis: id=hypothesis_id=H-ID, title=가설 title, status.

### 3.3 plan(state) 반환
`{'now': [...], 'next': [...], 'later': [...]}`. 각 리스트는 생성 순서(가설 dict 순) 안정.

### 3.4 render_plan_text
```
NOW
  [A-002] 개발자 인터뷰 (H-001 탐구 중)
  H-003 경쟁 가설 (반박 경합)
NEXT
  ...
LATER
  (없음)
```
빈 버킷은 "(없음)".

### 3.5 CLI
- `plan` 서브파서(+ `--text`). dispatch: `monitor.plan(replay(events))` → `--text`면 `render_plan_text`, 아니면 JSON.

## 4. 수용 기준 (TDD, tests/test_plan_view.py)
1. **NOW 분류:** exploring 가설의 열린 action + contested 가설(action 없음) → now.
2. **NEXT 분류:** suggested 가설(action 없음) + supported 가설의 열린 action → next.
3. **LATER 분류:** suspended 가설(+그 열린 action) → later.
4. **종결 제외:** refuted/human-closed/synthesized 가설·그 action은 어느 버킷에도 없음.
5. **done action 제외:** 완료된 action은 안 나옴.
6. **중복 방지:** 열린 action 있는 가설은 action만, 가설 레벨 중복 없음.
7. **활성 무-action 노출(critic gap1/2):** exploring(action 없음)→NOW 가설레벨, supported(action 없음)→NEXT 가설레벨. 누락 없음.
8. **text 렌더:** 버킷 헤더 NOW/NEXT/LATER, 빈 버킷 "(없음)".
9. **CLI JSON/text:** `plan`(JSON 3키), `plan --text`(헤더 포함).

(픽스처: supported/suspended/refuted는 `Commands.decide`(human) 경로로 — 에이전트는 contested/exploring edge만, critic NIT.)

전체 스위트 그린(기존 pre-existing 11 red 제외).

## 5. 작업 순서(TDD)
1. red: plan 분류 테스트 → 실패.
2. green: monitor.plan + render_plan_text.
3. CLI red→green.
4. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의
- §20 과확장 금지: 날짜/마감/우선순위 숫자 **추가 안 함** — 순수 상태 파생. 테스트/문구로 고정.
- contested가 NOW(resolve)와 review의 'resolve' 그룹과 개념 중복 — 의도적(같은 신호의 시간축 뷰). 상태 단일 진실원천 유지.
- 가설 dict 순서로 안정 정렬(생성 순) — review와 일관.

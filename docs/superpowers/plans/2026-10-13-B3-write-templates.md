# B3 — research-note · decision-record 템플릿 export (plan)

> 핸드오프 Track B/B3. Weekly(이미 있음)에 더해 **research note(근거·탐색 요약)**·
> **decision record(상태 전이·결정 사유)** 마크다운을 이벤트 로그에서 생성. weekly와 동일 패턴.

## 1. 목표 / 범위
- **목표:** `inquiry write research-note`·`write decision-record`가 로그 기반 마크다운 출력(stdout 또는 `--out`).
- **범위 밖:** 새 이벤트/상태 변경(순수 read-only 투영), NOW/NEXT/LATER(B2), TUI.

## 2. 현황 (코드 근거)
- `weekly.py`: `build(events, state, *, days, now)` → report dict → `render_markdown(report)`(§14 frontmatter
  `generated_from: {inquiry, through_event, generated_at}` + `_table`/`_cell` 표 + `STATUS_LABELS` + 빈 섹션 생략).
- CLI(cli.py:235-239, 494-508): `write` 서브파서, `write weekly --days --out`. dispatch는 `weekly`/`write` 공통 분기에서
  `build`→`render_*`, `--out`이면 `out.write_text(..., utf-8)` + `{"out": path}` JSON, 아니면 stdout.
- 공유 프리미티브: `weekly._cell`(파이프 이스케이프·공백정규화), `weekly._table`, `weekly.STATUS_LABELS`, `weekly._moment`.

## 3. 접근
새 모듈 `inquiry/notes.py` — weekly의 공유 헬퍼(`STATUS_LABELS, _cell, _table`)를 import해 DRY.
각 템플릿은 `build_*` (순수 투영) + `render_*` (마크다운, weekly와 동일 frontmatter).

### 3.1 research-note (근거·탐색 요약 — 현재 스냅샷)
- `build_research_note(events, state, *, now=None)` → dict:
  - 메타(inquiry_id, through_event, generated_at, question/purpose from frame).
  - `active`: 상태 ∈ {exploring, supported, contested}인 가설 — id·title·claim·status·confidence 요약.
    **confidence는 스칼라 아님**(critic G1): `monitor.assessment_summary(node)` 문자열(str|None) → None이면 '-'. 링크된 근거(관계·id·요약).
  - `evidence`: 전체 근거 카탈로그(id·type·관계링크·내용·uri). weekly evidence 셰이프 재사용(헬퍼로 추출).
  - `open`: suggested 가설(다음 탐색 후보).
- `render_research_note(report)`: frontmatter + 중심질문 + "활성 가설"(표: ID·제목·상태·confidence) +
  가설별 근거(불릿) + "근거 카탈로그"(표: ID·관계·유형·내용) + "탐색 후보(suggested)". 빈 섹션 생략.

### 3.2 decision-record (상태 전이·결정 사유 — 의사결정 로그)
- `build_decision_record(events, state, *, now=None)` → dict:
  - 메타 + `decisions`: 모든 `HypothesisStateChanged`를 시간순으로 — hypothesis_id·title·from→to·trigger·reason·
    actor·at·cited evidence_ids·reopen_if. (사람/에이전트 구분은 actor로.)
- `render_decision_record(report)`: frontmatter + 중심질문 + "결정"(표: 가설·변화(from→to)·트리거·행위자·사유) +
  종결 결정(refuted/human-closed)의 reopen_if는 별도 열/주석. 빈 로그면 "(결정 없음)".

### 3.3 CLI 배선 (critic B1 교정)
- `write_subs`에 `research-note`·`decision-record` 서브파서(각 `--out`). `--days` 없음.
- **dispatch는 `build` 호출 전에 `args.operation`으로 분기**(현행처럼 무조건 `weekly.build(days=args.days)` 호출 금지 —
  신규 서브커맨드엔 `args.days`가 없어 AttributeError, 빌더·렌더러도 다름). `getattr(args,'days',7)` 폴백은 **사용하지 않음**(red herring).
  - `weekly`(text, --out 없음) / `write weekly`(markdown, --days·--out) 경로는 **그대로 유지**(혼동 금지).
  - `write research-note` → `build_research_note`/`render_research_note`; `write decision-record` → `build_decision_record`/`render_decision_record`.
  - `--out`/stdout 출력 로직만 공통 헬퍼로.

## 4. 수용 기준 (TDD, tests/test_write_templates.py)
1. **research-note 생성:** exploring 가설 + 근거 링크된 inquiry → 마크다운에 frontmatter(generated_from)·중심질문·
   활성 가설 표(가설 ID·상태)·근거 내용 포함.
2. **research-note 빈 탐색:** 가설 없으면 활성/근거 섹션 생략, 예외 없음.
3. **decision-record 생성:** start→support 등 전이가 있는 로그 → 결정 표에 from→to·trigger·reason·actor 포함.
4. **decision-record 종결 reopen_if:** close한 가설의 reopen_if가 렌더에 노출.
5. **decision-record 빈 로그:** 전이 없으면 "(결정 없음)", 예외 없음.
6. **--out 파일 출력:** `write research-note --out path` → 파일 생성 + `{"out": path}` JSON(기존 weekly와 동일).
7. **에이전트 귀속 표시:** agent push로 contested된 전이의 actor가 `agent:<name>`로 표시.
8. **회귀:** 기존 weekly(`write weekly`, `weekly`) 동작·테스트 불변.

전체 스위트 그린(기존 pre-existing 11 red 제외).

## 5. 작업 순서(TDD)
1. red: research-note 생성/빈 → 실패.
2. green: notes.build_research_note + render + CLI.
3. decision-record red→green.
4. --out·귀속·회귀.
5. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의
- weekly 헬퍼 import(underscore): 내부 재사용이라 허용하되, 깨지면 notes 로컬 복제로 폴백.
- CLI dispatch에 `weekly`/`write` 공통 분기가 `args.days`를 가정 — 신규 서브커맨드는 days 없음 → `getattr(args,'days',7)`로 안전.
- read-only 불변: 어떤 이벤트도 쓰지 않음(테스트로 재확인).

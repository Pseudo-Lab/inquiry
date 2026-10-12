# A2 — MCP tool 확장: assessment·contested push (plan)

> 핸드오프 Track A/A2. 에이전트(외부 harness)가 더 많은 연산을 push: (a) assessment(D3 채점 결과),
> (b) agent-허용 전이(contested 표시, `_AGENT_EDGES` 내). **터미널 전이(refute/close/synthesize)는 노출 금지**(사람 전용).

## 1. 목표 / 범위
- **목표:** `IngestService`에 `assess`·`contest` 추가, `mcp_server`에 `inquiry_assess`·`inquiry_contest` tool.
- **범위 밖:** structured_content(A3), usage 보고(A4), 부트스트랩(A5), TUI.

## 2. 현황 (코드 근거)
- `IngestService`(ingest/service.py): agent 귀속 `_commit`(actor=`agent:<name>`, 동시성 재시도). 이미 `add_hypothesis`·`add_evidence`.
- **assessment 이벤트:** `HypothesisAssessed`(events.py:41 필드 `kind,hypothesis_id,run_id,assessment`). 검증: `validate_assessment`(5축 전부, 미채점 null) + 이벤트레벨 `run_id` nonempty text.
  replay(replay.py:193-204)는 **run_id를 state.runs에서 조회하지 않음** → 에이전트 push는 합성 run_id(`R-`+uuid)로 가능. 각 축 `_check_refs`로 evidence_refs가 **링크돼 있어야**.
- **contested 전이:** `HypothesisStateChanged` to `contested`. `_AGENT_EDGES`(transitions.py:16) = {(exploring,contested),(supported,contested),(contested,exploring)} → **에이전트 허용**.
  replay(replay.py:161-171): `validate_transition`가 role=agent로 `_AGENT_EDGES` 강제 + `cited` evidence가 **challenges 관계로 링크**돼야(line 167-171). change의 actor·at은 event와 일치해야(line 152).
- **기존 에러-반환 패턴**(add_evidence, mcp_server.py:46-58): 예외를 `{error, hint, allowed_*}`로 반환(MCP가 raise 메시지를 삼키므로). A2도 동일 패턴.
- 축 payload 형태(schema.py): `{low,high,source,evidence_refs,unverified,rationale}`, source∈{agent-estimate,human-judgment,measured-result}. source 단조성은 replay 비강제(ref 존재/링크만).

## 3. 접근

### 3.1 IngestService.assess_axis(target, axis, low, high, rationale, evidence_refs=(), unverified=True)  ★critic B1 교정
- **전체 replace(HypothesisAssessed) 금지** — agent-estimate가 기존 human/measured 평가와 미제공 축을 덮어쓰기 때문.
  대신 **축별 `ConfidenceUpdated`**(replay.py:205-212 per-axis replace로 다른 축 보존) 1건 emit.
- `source`는 **항상 `'agent-estimate'`로 강제**(에이전트는 정의상 agent-estimate; human/measured 참칭 금지).
- payload = `{low, high, source:'agent-estimate', evidence_refs:list, unverified:bool, rationale}` → `validate_axis`로 폼 검증.
- **단조성 가드(서비스 레벨):** `node.assessment`의 해당 축이 이미 scored이고 그 `source` 랭크 > 0(human/measured)면
  ValueError('cannot downgrade <axis> from <source>')로 거부. null 또는 agent-estimate면 허용(덮어쓰기 OK).
- `ConfidenceUpdated(hypothesis_id, run_id='R-'+uuid, axis, score=payload)` 커밋(agent 귀속). run_id는 합성(state.runs 미참조 확인됨).
- target 미존재/ref 미링크는 replay가 커밋 시 ValueError → tool에서 구조화 에러.

### 3.2 IngestService.contest(target, reason, evidence_id)
- `HypothesisStateChanged` change: `from`=현재 상태(build에서 state로 조회), `to`='contested', `trigger`='contest',
  `actor`=self.actor, `at`=커밋 at, `reason`, `evidence_ids`=[evidence_id], `evidence_snapshot`=None, `reopen_if`=None, `synthesis_target`=None.
- 커밋 시 replay가 `_AGENT_EDGES`·challenges-링크·reason 강제. 위반은 ValueError.
- `_current_status` 조회를 위해 build(state, at) 내부에서 `state.hypotheses[target].status` 사용(미존재면 ValueError).

### 3.3 MCP tools (mcp_server.py, dep-free 핸들러 + build_server 등록)
- **축 1개씩 타입드 파라미터**(critic Q5: dict 파라미터는 input_schema 불투명 → 회피):
  `assess(root, agent, target, axis, low, high, rationale, evidence_refs=None, unverified=True)` 핸들러 → `IngestService.assess_axis`.
  tool `inquiry_assess(target, axis: Literal[5축], low: float, high: float, rationale: str, evidence_refs: Optional[list]=None, unverified: bool=True)`.
  예외는 `{error, hint, allowed_axes, note:"agent pushes are always agent-estimate; cannot downgrade a human/measured axis"}` 반환.
- `contest(root, agent, target, reason, evidence_id)` 핸들러 → IngestService.contest. 예외는 `{error, hint}`(challenges 링크·상태 전제 안내).
- `build_server`에 `@server.tool()`로 `inquiry_assess`·`inquiry_contest` 등록. **터미널 전이 tool은 추가하지 않음**(사람 전용 불변식).
  → 기존 `test_build_server_registers_tools`(3-tool 하드코딩)를 **2개 추가 반영해 갱신**(critic G1, skipUnless(_MCP_AVAILABLE)).
- MCP 2.x: 핸들러는 순수 Python(테스트는 handler 직접), 타입힌트로 input_schema 생성(snake_case 유지).

## 4. 수용 기준 (TDD)
`tests/test_mcp_agent_push.py`(신규). 핸들러를 **mcp 패키지 없이** 직접 호출(dep-free).

1. **assess 정상:** 가설에 `assess(target, 'plausibility', 0.4, 0.7, '근거 요약')` → ConfidenceUpdated 기록, source='agent-estimate', **다른 축 보존**(미제공 축 불변). replay 반영(node.assessment.plausibility 존재).
2. **assess 폼 에러:** low>high → `{error, hint}` 반환(raise 아님), 상태 불변.
3. **assess evidence_refs 미링크:** 링크 안 된 evidence_ref → 구조화 에러.
4. **assess 단조성 가드(★):** 축이 이미 human-judgment면 agent push가 **거부**(downgrade 금지), 기존 평가 불변.
5. **contest 정상:** exploring 가설 + challenges 근거 링크 후 `contest(target, reason, evidence_id)` → 상태 contested, actor=agent:<name>.
6. **contest 전제 위반:** suggested 가설 contest → 구조화 에러("not allowed", human-targets 체크가 agent-edge보다 먼저, critic G2), 상태 불변.
7. **contest 근거 누락:** challenges 링크 없이 contest → 에러.
8. **터미널 전이 미노출(도메인 보장):** contest가 **비허용 edge를 거부**함(수용6)이 진짜 불변식. 추가로 mcp 설치 시 등록 tool 집합 == 기존3+{assess,contest}(skipUnless), refute/close/synthesize 부재.
9. **agent 귀속:** 커밋 이벤트 actor == `agent:<name>`.

전체 스위트 그린(기존 pre-existing 11 red 제외).

## 5. 작업 순서(TDD)
1. red: assess 정상/폼에러 → 실패.
2. green: normalize_assessment + IngestService.assess + handler.
3. contest red→green.
4. 터미널 미노출·귀속 테스트.
5. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의
- `validate_assessment`는 5축 전부 요구 → normalize가 누락 축 null 채움(핵심). 테스트로 고정.
- contest의 challenges-링크 요구(replay.py:167-171)를 수용4 전제에 반영.
- run_id 합성이 replay 불변식 안 깨는지(state.runs 미참조 확인됨) — 테스트로 재확인.
- mcp 2.x 핸들러 분리 유지: `assess`/`contest` 순수 함수 + build_server 등록만 tool.

# A4 — 외부 사용량/비용 보고 (harness→inquiry) (plan)

> 핸드오프 Track A/A4. harness(에이전트)가 토큰/비용을 inquiry에 보고 → 모니터에 노출(피벗 모드 spend 가시성).
> D6 spend cap은 **self-run 한정**이므로 pivot은 "모니터"(집계·표시)만. 강제 차단 아님.

## 1. 목표 / 범위
- **목표:** `inquiry_report_usage` MCP tool → `AgentUsageReported` 이벤트(agent 귀속) → monitor 집계 → TUI 요약바 표시.
- **범위 밖:** spend cap 강제(self-run용 D6), 가격 계산 로직(보고된 est_cost만 합산), 결제.

## 2. 현황 (코드 근거)
- usage 셰이프: `validate_usage`(llm/adapter.py) — `{status, input_tokens, output_tokens, est_cost, price_ref}`.
  known은 nonneg int 토큰, est_cost는 nonneg(주면 price_ref 필수), null 허용.
- 기존 usage 이벤트 `RunUsageReported`/`RunSucceeded`.usage는 **self-run(Runner)** 전용(D6 budget_status, runs.py:42).
- 이벤트 검증(events.py:140): `CHANGE_FIELDS[kind]`로 정확한 필드셋 강제. replay 디스패치(replay.py:280 else)는 inquiry 존재 요구 후 `_apply_domain`; 미지 kind는 **no-op**(domain 체인에 없으면). `is_agent_actor`(replay.py:8) 사용 가능.
- `monitor.summary`(monitor.py:27)는 events를 스캔해 agents·agent_last_seen 집계. `control_summary_text`가 TUI 요약바 1줄 생성.
- TUI(tui.py `_reload_state`)가 `monitor.summary` → `_update_summary` → `control_summary_text` 호출.

## 3. 접근

### 3.1 새 이벤트 AgentUsageReported
- `CHANGE_FIELDS += {'AgentUsageReported': frozenset({'kind', 'usage'})}`. actor는 **이벤트 레벨**(agent:<name>, IngestService가 설정) — 기존 agents 집계와 일관.
- events.py 검증 branch: `validate_usage(change['usage'])` + `status == 'known'` 요구(RunUsageReported와 동일 기준).
- replay.py 디스패치에 **명시적 branch**: inquiry 존재 + `is_agent_actor(event['actor'])` 요구(사용량은 에이전트 귀속), state 변경 없음(no-op projection; 집계는 monitor가 이벤트에서).

### 3.2 IngestService.report_usage(input_tokens, output_tokens, est_cost=None, price_ref=None)
- `usage = {status:'known', input_tokens:int, output_tokens:int, est_cost, price_ref}` → `AgentUsageReported` 커밋(agent 귀속).
- 음수/비정수 토큰, est_cost 있는데 price_ref 없음 등은 validate_usage가 커밋 시 ValueError.

### 3.3 monitor 집계
- `_usage(events)` 헬퍼: AgentUsageReported를 스캔해 `by_agent[agent] = {input, output, est_cost}` 합산 + `total = {input, output, est_cost, reports}`. est_cost는 null 제외 합(일부만 비용 보고해도 합산).
- `summary(...)` 반환 dict에 `usage=_usage(events)` 추가(기존 키 불변 — 순수 확장).
- `control_summary_text`에 total 토큰(+비용 있으면) 1줄 꼬리 추가. 기존 포맷 뒤에 ` · usage N tok`(비용 있으면 `/$X`).

### 3.4 MCP tool
- 핸들러 `report_usage(root, agent, input_tokens, output_tokens, est_cost=None, price_ref=None)` → IngestService.report_usage. 예외는 `{error, hint}`(토큰 nonneg int, est_cost엔 price_ref 필요).
- `build_server`에 `inquiry_report_usage(input_tokens:int, output_tokens:int, est_cost:Optional[float]=None, price_ref:Optional[str]=None)` tool. 기존 tool 등록 테스트 집합에 추가.

### 3.5 TUI
- 변경 없음(자동) — `_update_summary`가 `control_summary_text`를 그대로 호출, usage는 summary에 포함돼 요약바에 반영. (회귀 테스트로 요약바에 usage 노출 확인.)

## 4. 수용 기준 (TDD, tests/test_usage_reporting.py)
1. **report_usage 집계:** 에이전트가 2회 보고(1000/500, 2000/700) → monitor.summary['usage'] total input=3000, output=1200, reports=2.
2. **by_agent 분리:** 두 에이전트 보고 → by_agent에 각 합산.
3. **비용 합산:** est_cost+price_ref 보고 → total.est_cost 합; 일부만 비용이면 그 합만.
4. **폼 에러:** 음수 토큰 or est_cost만(price_ref 없음) → `{error, hint}`, 이벤트 미기록.
5. **에이전트 귀속:** 보고 이벤트 actor == agent:<name>; 사람 actor로는 AgentUsageReported replay 거부.
6. **control_summary_text:** usage 있으면 요약바 문자열에 토큰 수 포함.
7. **tool 등록:** inquiry_report_usage가 build_server 등록 집합에 포함(skipUnless mcp).
8. **기존 불변:** summary 기존 키·D6 budget_status·기존 테스트 불변(순수 확장).

전체 스위트 그린(기존 pre-existing 11 red 제외).

## 5. 작업 순서(TDD)
1. red: report_usage 집계/by_agent → 실패.
2. green: 이벤트+검증+replay branch + IngestService.report_usage + monitor._usage/summary.
3. 비용·폼에러·귀속·control_summary·tool 등록 red→green.
4. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의
- **spend cap 혼동 금지:** A4는 모니터링(집계·표시)만. D6 self-run cap 강제와 분리 — AgentUsageReported는 budget_status(runs.usage)에 섞지 않음(별도 집계).
- 새 이벤트 CHANGE_FIELDS 정확 필드셋 — `{kind, usage}`만.
- replay no-op이지만 inquiry 존재·agent actor 불변식은 명시적으로 강제(테스트5).
- control_summary_text 포맷 변경이 기존 테스트를 깨지 않게 — 꼬리 추가(기존 접두 보존), usage 0이면 생략.

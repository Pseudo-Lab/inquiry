# MCP 서버 활동 로깅 (plan)

> 세션ID 없이 "에이전트가 inquiry에 뭘 했나"를 보려면 MCP 서버가 자기 tool 호출·결과를 데이터 폴더에
> append-only로 로깅해야 한다. `tail <dir>/mcp-activity.jsonl`로 자가 디버깅.

## 1. 목표 / 범위
- **목표:** 각 MCP tool 호출마다 `<root>/mcp-activity.jsonl`에 한 줄 append: `{at, agent, tool, ok, error?, args}`.
- **범위 밖:** CLI(사람) 호출 로깅(얘는 MCP 전용), 이벤트 로그(store.jsonl) 변경, 민감정보 암호화.

## 2. 현황 (코드 근거)
- `build_server(root, agent)`가 7개 tool을 `@server.tool(structured_output=True)` 데코레이터로 등록(mcp_server.py). 각 tool은 모듈 핸들러(add_hypothesis/assess/contest/report_usage/propose_frame/add_evidence/status) 호출 후 dict 반환.
- 핸들러 중 일부는 성공 `{ok:...}`/`{hypothesis_id}`, 실패는 `{error, hint}` 반환(구조화 에러 패턴).
- `status` 핸들러는 CLI와 MCP tool **둘 다** 호출 → 핸들러 레벨 로깅은 CLI 호출까지 섞임. **tool 래퍼 레벨에서 로깅**해야 MCP만 잡음.

## 3. 접근
- **모듈 함수(테스트 가능) `append_activity(root, agent, tool, args, result)`**:
  - `ok = not (isinstance(result, dict) and 'error' in result)`.
  - entry `{at: now iso, agent, tool, ok, args: _summarize(args)}`, 실패면 `error: result['error']` 추가.
  - `_summarize(args)`: dict를 json으로 직렬화하되 값이 긴 문자열이면 절단(예: 120자)해 로그 비대화 방지.
  - `<root>/mcp-activity.jsonl`에 append. **실패해도 절대 raise 안 함**(tool 호출을 로깅이 깨지 않게 try/except). result를 그대로 반환.
- **build_server에서 각 tool 본문 안에서 호출**(시그니처 래핑 금지 — critic 주의: `@server.tool`이 시그니처로 input_schema를 생성하므로 `functools.wraps(**kwargs)` 래핑은 스키마를 깨뜨릴 수 있음).
  - 패턴: `return append_activity(root, agent, 'inquiry_x', {요약 인자}, handler(...))`.
  - 7개 tool 각각 한 줄 수정(핸들러 결과를 append_activity로 감싸 반환).
- 로그 위치는 데이터 폴더 루트(`root`), append-only JSONL(이벤트 소싱 철학과 일치).

## 4. 수용 기준 (TDD, tests/test_mcp_activity_log.py)
1. **성공 로깅:** `append_activity(root,'claude-1','inquiry_status',{},{'hypotheses':1})` → 파일에 한 줄, `ok:true, agent, tool, at` 포함.
2. **에러 로깅:** result가 `{error:'x'}` → `ok:false`, `error:'x'` 기록.
3. **append 누적:** 두 번 호출 → 2줄.
4. **로깅 실패 무해:** 쓸 수 없는 root(예: 파일인 경로)여도 raise 안 하고 result 반환.
5. **args 절단:** 아주 긴 문자열 인자는 로그에서 절단.
6. **(skipUnless mcp) 실서버 경로:** build_server→call_tool('inquiry_status') 후 `<root>/mcp-activity.jsonl`에 `inquiry_status` 줄 생김. 입력스키마/등록 tool 집합 불변(7개).
7. **회귀:** 기존 tool 반환값·structured_content 불변(append_activity는 result 그대로 반환). 전체 253 그린.

## 5. 작업 순서(TDD)
1. red: append_activity 성공/에러/누적 → 실패.
2. green: append_activity + build_server 7개 tool 배선.
3. 실서버 로그 생성·회귀.
4. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의 (critic 반영)
- **시그니처 보존(B2 교정)**: `functools.wraps`는 `__wrapped__`로 시그니처를 **보존**하므로 schema는 안 깨지지만, `wraps` 없는 `**kwargs` 래퍼는 깨뜨린다. 논쟁 자체를 피하려 **본문 내 로깅**(inspect.signature에 안 보임)으로 간다.
- **경로(B1 교정)**: 이벤트 로그는 `<root>/.inquiry/events.jsonl`(store.py). 활동 로그는 `<root>/mcp-activity.jsonl`(데이터 폴더 루트, 사람이 `tail`하기 쉬움). replay/Store는 이 파일을 안 읽음(iterdir 없음) → 안전. "이벤트 로그 옆"이 아니라 **데이터 폴더 루트에 사람용 로그**.
- **폴더 부재(G3)**: 첫 호출이 read-only(status)면 `.inquiry/`가 없을 수 있음. `append_activity`가 open 전에 `Path(root).mkdir(parents=True, exist_ok=True)`를 try 안에서 수행. 쓸 수 없으면 조용히 무시.
- **add_hypothesis 실패는 로깅 안 됨(G1)**: 이 핸들러만 try/except가 없어 ValueError가 raise됨 → append_activity 도달 전. 다른 6개는 `{error}` dict 반환이라 로깅됨. (성공 호출은 모두 로깅.) best-effort 로그의 알려진 한계로 남김.
- **로깅은 best-effort**: 어떤 I/O 에러도 tool 결과를 막지 않게 try/except. result 그대로 반환.
- **동시성(N4)**: 여러 세션이 같은 파일에 append. args 절단(값당 ~120자)으로 한 줄이 작아 append가 대체로 원자적(PIPE_BUF). 이벤트 로그와 달리 fcntl/재시도 없는 best-effort — 드물게 interleave 가능, 허용.
- `at`은 `datetime.now(timezone.utc).isoformat()`(집 스타일). status가 CLI·MCP 공용이므로 **tool 래퍼에서만** 로깅.

# A3 — MCP structured_content (plan)

> 핸드오프 Track A/A3(낮음, polish). tool 반환을 structured_content로(현재 text JSON만). 에러도 구조화(이미 패턴 존재).

## 1. 목표 / 범위
- **목표:** 모든 inquiry MCP tool 결과가 `structured_content`로 전달되게(현재는 TextContent JSON만, structured_content=None).
- **범위 밖:** 엄격 output schema(JSON Schema) 강제, 핸들러 로직 변경, TUI.

## 2. 현황 (코드 근거, 실측)
- mcp 2.x `MCPServer.tool(..., structured_output: bool|None=None)`. 반환 annotation으로 구조화 판단.
- **실측:** `@server.tool()` + `-> dict` → 결과 `structured_content=None`(TextContent JSON만).
  `@server.tool(structured_output=True)` + `-> dict[str, Any]` → `structured_content={...}` 채워짐 + TextContent 유지.
  `-> dict`(bare) + structured_output=True → `InvalidSignature: dict is not serializable for structured output`(bare dict 불가, 파라미터화 필요).
- 현재 6개 tool(add_hypothesis/add_evidence/status/assess/contest/report_usage)은 `@server.tool()` + `-> dict`.
- 핸들러는 성공/{error,hint} 모두 dict 반환(이미 구조화 에러 패턴, add_evidence 등).

## 3. 접근
- `from typing import Any` 추가.
- 6개 tool 각각: `@server.tool()` → `@server.tool(structured_output=True)`, 반환 annotation `-> dict` → `-> dict[str, Any]`.
- 핸들러 로직·입력 스키마(Literal 등) 불변. outputSchema는 `dict[str, Any]`라 느슨(NONE) — 이질적 {ok,...}/{error,hint} 모두 OK(엄격 검증 없음, 의도).

## 4. 수용 기준 (TDD, tests/test_mcp_structured.py, skipUnless mcp)
1. **성공 결과 structured:** build_server→`call_tool('inquiry_status', {...})` 결과 `structured_content`가 dict이고 요약 키 포함.
2. **에러 결과 structured(critic B1):** 서비스 레벨 실패 — `inquiry_add_evidence` target 미존재(또는 uri 없는 external-article) → `structured_content`에 `error`·`allowed_evidence_types`.
   ※ Literal 밖 값(잘못된 evidence_type/axis)은 **프레임워크가 핸들러 전 거부**(ToolError)라 structured 없음 — 테스트에 쓰지 않음.
3. **assess/contest/report_usage structured:** 성공 시 structured_content 존재. assess 에러는 low>high(서비스 레벨)로.
4. **회귀:** 등록 tool 집합·입력 스키마(Literal 값)·tool 이름 불변. (단 §5 known red `inputSchema` 테스트는 pre-existing 11 red에 포함 — A3와 무관, 계속 red.)

전체 스위트 그린(기존 pre-existing 11 red 제외).

## 5. 작업 순서(TDD)
1. red: structured_content 존재 테스트 → 실패(현재 None).
2. green: structured_output=True + dict[str, Any].
3. 에러 경로·회귀.
4. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의
- bare `dict`는 structured_output과 비호환 → 반드시 `dict[str, Any]`.
- outputSchema 느슨(검증 없음) — 이질적 반환(success/error) 허용이 목적. 엄격 스키마는 범위 밖.
- 기존 §5 known issue(test_mcp_and_status `inputSchema→input_schema`)는 **건드리지 않음**(별도 cleanup).

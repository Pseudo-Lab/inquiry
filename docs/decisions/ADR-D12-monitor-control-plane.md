# ADR-D12 — inquiry = 다중 에이전트 탐구의 monitor/control-plane (방향 전환)

- 상태: **Accepted** (2026-10-12 방향 전환 확정; 구현은 단계별)
- 작성일: 2026-10-12
- 관련: PRODUCT-CONCEPT §5·§11 · MILESTONES §M3 · 일부 재해석: D4(agent-adapter)·D8(로컬 BYOK) · 재사용: D1·D2·D3·D5·D10·D11 · 구현 계획: [pivot Phase 0–1](../superpowers/plans/2026-10-12-pivot-phase0-1.md)

## 맥락

M2~M3까지 inquiry는 **스스로 BYOK로 LLM을 호출해 가설을 생성하는 agent runner**였다(D3 confidence·D6 spend cap·D10 다중 actor·D11 dedup 모두 이 전제). 그러나 어댑터가 **도구 없는 단일 구조화 호출**(`responses.create`에 `tools=` 없음)이라, "외부 레퍼런스를 가져오는 리서치 커넥터"가 원천적으로 불가능하다(모델은 input에 넣어준 것만 본다).

한편 사용자의 **harness 에이전트(Claude Code/Codex/orca 세션)**는 이미 웹검색·도구·파일·추론 루프를 갖췄다. 생성을 그쪽에 맡기면 리서치 커넥터가 공짜로 해결된다. 그리고 제품 니치가 "또 하나의 BYOK 가설 생성기"보다 **"에이전트 팀이 공유하는 구조화된 탐구 지도/메모리"**(PRODUCT-CONCEPT §5 "사람과 여러 AI 에이전트가 함께 일하는 팀")가 더 차별화된다.

## 결정

**inquiry를 agent runner에서 "공유 구조화 탐구 그래프 + MCP 인제스천 + 멀티에이전트 모니터(control-plane)"로 전환한다.** 가설 생성은 외부 harness 에이전트가 하고, inquiry는 그 산출물을 받아 추적·모니터링한다.

- **세션 모델 = 공유 그래프.** 하나의 inquiry 그래프에 여러 에이전트가 `agent:<name>`(세션 정체성)로 참여한다. dir-per-session이 아니라 공유 그래프 — 교차 dedup(D11)·synthesis가 자연스럽다.
- **인제스천 = MCP 서버.** inquiry가 hypothesis/evidence push + status/graph/saturation read를 MCP tool로 노출(`inquiry mcp --agent <name>`). 에이전트 커밋은 `agent:<name>` actor로 기록된다. (`src/inquiry/mcp_server.py`, 핸들러는 `IngestService`/`monitor` 위의 얇은 래퍼. `mcp` 패키지는 OpenAI SDK처럼 optional·lazy.)
- **사람-에이전트 분업은 D5 상태머신 + D10 actor가 이미 강제.** 에이전트는 `_AGENT_EDGES` 내 제안/탐색만 — refute/close/synthesize 같은 터미널 결정은 사람이 모니터에서 확정(`human:local`). 이 전환은 D5/D10 위에 그대로 올라탄다.
- **self-run 모드 보존.** `openai_adapter`·`Runner`·spend-cap(D6)는 삭제하지 않고 **optional self-run 모드**로 둔다. pivot 모드에선 에이전트가 MCP로 직접 커밋(in-process Run 미경유).
- **세션/pane 관리는 orca.** inquiry는 세션 매니저를 다시 만들지 않고 **상태 + 모니터 뷰**(`inquiry status`)만 제공한다.

## 근거 (provenance)

- harness 에이전트가 웹·도구를 이미 보유한다는 외부 사실 → 리서치 커넥터 재구현 불필요.
- PRODUCT-CONCEPT §5·§11(에이전트 팀)의 직접 구현.
- 코어(이벤트 소싱 D1, 그래프 D2, confidence D3, 상태머신 D5, actor D10, dedup D11)가 생성 주체와 무관하게 재사용됨 — 전환 비용이 낮다(Phase 1에서 코어 변경 0, 추가만).

## 결과 · 트레이드오프

- **코어 ~90% 재사용.** 새 코드는 `features/ingest/`(agent 귀속 커밋)·`monitor.py`(요약)·`mcp_server.py`(lazy)·`inquiry status`뿐.
- **D4(agent-adapter)**: in-process 어댑터는 이제 self-run 모드 **한정**. pivot의 "생성"은 어댑터 밖(harness).
- **D8(로컬 BYOK)**: self-run 모드는 BYOK 유지. pivot 모드는 **harness가 키를 보유** → inquiry 자체는 키 불필요. D8을 "self-run 한정"으로 범위 축소.
- **D6 spend cap**: in-process 토큰 차단은 self-run 한정. pivot 모드의 사용량/비용은 harness 보고에 의존(후속, 현재는 미추적).
- 사람 결정 게이트가 명시화됨(에이전트 제안 → 사람 확정) — 자율성과 통제의 균형(§4.4·§19).

## 대안 (기각)

- **자급 runner + tool-use 루프/web_search 내장:** 도구 루프·재시도·비결정성·비용을 직접 떠안아야 함. harness 재사용이 코드가 훨씬 적다.
- **harness를 어댑터로 shell-out:** 가능하나 결정성·배포가 복잡. MCP 인제스천이 더 표준적이고 에이전트 native.
- **dir-per-session:** 격리는 깔끔하나 교차 그래프 이점(공유 dedup·synthesis)을 잃음.

## 열린 질문

- **모니터 심화:** `inquiry status`(JSON)를 넘어 TUI 대시보드를 inquiry가 가질지 vs orca가 상태를 읽어 렌더할지. (Phase 2)
- **외부 사용량/비용 보고:** harness→inquiry로 토큰/비용을 전달해 모니터링할 방식. (후속)
- **MCP tool 표면 확장:** 에이전트-허용 상태 전이(contested 표시 등) push, assessment push를 tool로 열지. (Phase 1.5)
- **D8 갱신 문서화:** BYOK 결정을 "self-run 한정"으로 정식 개정할지.
- **에이전트가 inquiry를 부트스트랩** 가능하게 할지(현재는 사람이 `init`).

# ADR-D3 — Confidence 데이터 모델 + Provenance

- 상태: **Proposed**
- 작성일: 2026-08-28
- 관련: PRODUCT-CONCEPT §4.3 §6.4 §20(가짜 정밀도) §21.10 · REVIEW 1-③

## 맥락

원문 §6.4는 스칼라(`plausibility: 0.72`)와 범위(`range: [0.50, 0.80]`)를 동시에 쓰지만, "누가·언제·어떻게 업데이트하는가"와 인용 규격이 없다. §20의 "가짜 정밀도" 위험과 직결.

## 결정

**단일 점수 대신 범위 + 출처(provenance)를 필수로 한다.**

- **평가 필드:** `plausibility`, `evidence_strength`, `novelty`, `impact`, `testability` 등은 각각 **범위 `[low, high]`** 로 저장. 단일 점수 표시 금지(요약 표시가 필요하면 범위의 중앙값을 *파생*으로만).
- **출처(source) 필수:** `agent-estimate` / `human-judgment` / `measured-result` 중 하나를 반드시 기록.
- **evidence_strength ↔ plausibility 분리:** 그럴듯함과 근거 강도를 절대 합치지 않는다.
- **업데이트 규칙:**
  - 값은 이벤트로만 변경(D1 정합) — `{field, from, to, source, actor, at, evidence_ref?}`.
  - `agent-estimate`는 새 evidence가 붙을 때 재추정 제안만 하고 **자동 확정하지 않음**(사람 또는 규칙이 승인).
  - 시간 경과 decay는 값 자체를 바꾸지 않고 §12 `outdated`/`stale` 신호로 표시(값과 신선도 분리).
- **인용 규격(provenance):** evidence에 `{type, uri?, quote?, retrieved_at, confidence_of_source?}`. 외부 근거는 출처·수집 시점 필수.

## 근거

- 원문 철학 §4.3(확신을 진실처럼 표현하지 않음)의 직접 구현.
- 범위+출처는 §20 "가짜 정밀도" 완화의 핵심 장치.

## 결과 · 트레이드오프

- UI는 색/기호 외에 범위와 출처 배지를 함께 노출해야 함(§9 접근성과 정합).
- 입력 부담↑ → 에이전트가 기본값(범위+출처) 채우고 사람이 교정하는 흐름으로 완화.

## 열린 질문

- 여러 evidence를 종합해 범위를 재계산하는 집계식을 규칙으로 둘지, 사람 판단으로 둘지 → M3에서 실측 후 결정.

# ADR-D3 — Confidence 데이터 모델 + Provenance

- 상태: **Accepted** (구조·원칙 확정; 축별 앵커 문구는 v0 초안이며 사례 축적으로 calibration — D5·D6과 동일 패턴)
- 작성일: 2026-08-28
- 관련: PRODUCT-CONCEPT §4.3 §6.4 §20(가짜 정밀도) §21.10 · REVIEW 1-③ · rubric 운영: [`assess-hypothesis` 스킬](../../.claude/skills/assess-hypothesis/SKILL.md)

## 맥락

원문 §6.4는 스칼라(`plausibility: 0.72`)와 범위(`range: [0.50, 0.80]`)를 동시에 쓰지만, "누가·언제·어떻게 업데이트하는가"와 인용 규격이 없다. §20의 "가짜 정밀도" 위험과 직결.

## 결정

**단일 점수 대신 범위 + 출처(provenance)를 필수로 한다.**

- **평가 필드:** `plausibility`, `evidence_strength`, `novelty`, `impact`, `testability` 등은 각각 **범위 `[low, high]`** 로 저장. 단일 점수 표시 금지(요약 표시가 필요하면 범위의 중앙값을 *파생*으로만).
- **[원칙 1] 연속 점수가 아니라 관찰 가능한 앵커 사다리로 분류한다.** 각 축은 `[0~1]` 확률을 *추정*하는 게 아니라, 관찰 가능한 기준으로 정의된 이산 등급(L0…L4)으로 매긴다. 채점자(사람·에이전트)의 일은 "확률 추정"이 아니라 "어느 등급의 기준을 충족하는가"의 대조·분류. 저장 숫자는 등급의 *파생 라벨*이며, 범위 `[low, high]`는 **인접 등급 간 불확실성**을 뜻한다(임의 폭 금지). 앵커 기준에는 주관어("그럴듯하면")가 아니라 evidence로 대조 검증 가능한 관찰만 쓴다.
- **출처(source) 필수:** `agent-estimate` / `human-judgment` / `measured-result` 중 하나를 반드시 기록.
- **[원칙 3] source 신뢰 위계 명시:** `agent-estimate` < `human-judgment` < `measured-result`. agent-estimate는 제안일 뿐 자동 확정하지 않으며(사람 승인 필요), 실험이 진행되면 근거를 `measured-result`로 **승격**한다.
- **evidence_strength ↔ plausibility 분리:** 그럴듯함과 근거 강도를 절대 합치지 않는다.
- **업데이트 규칙:**
  - 값은 이벤트로만 변경(D1 정합) — `{field, from, to, source, actor, at, evidence_ref?}`.
  - `agent-estimate`는 새 evidence가 붙을 때 재추정 제안만 하고 **자동 확정하지 않음**(사람 또는 규칙이 승인).
  - 시간 경과 decay는 값 자체를 바꾸지 않고 §12 `outdated`/`stale` 신호로 표시(값과 신선도 분리).
- **인용 규격(provenance):** evidence에 `{type, uri?, quote?, retrieved_at, confidence_of_source?}`. 외부 근거는 출처·수집 시점 필수.
- **[원칙 2] evidence는 시스템 밖에 독립적으로 존재하는 것만 인정한다.** `evidence.type`은 허용 목록으로 제한: `external-article` · `measured-result` · `human-interview` · `human-judgment` · `dataset`. LLM/에이전트의 자체 의견·결론은 근거가 될 수 없다(**`llm-opinion` 금지** — 순환 방지). 에이전트가 외부 자료를 검색·요약해 가져오는 것은 허용되나, 그때 근거는 *그 외부 자료*(uri·quote)이고 에이전트는 운반책일 뿐이다. **판정 기준: LLM이 사라져도 남아 있는 것만 evidence.**
- **rubric 운영 위치:** 위 원칙(구조·계약)은 이 ADR에 **동결**. 축별 앵커 사다리 문구 + calibration 사례는 [`assess-hypothesis` 스킬](../../.claude/skills/assess-hypothesis/SKILL.md)에서 유지하며 사례 축적으로 정교화한다(스킬이 D3를 대체하지 않고, D3가 가리키는 살아있는 부속물).

## 근거

- 원문 철학 §4.3(확신을 진실처럼 표현하지 않음)의 직접 구현.
- 범위+출처는 §20 "가짜 정밀도" 완화의 핵심 장치.

## 결과 · 트레이드오프

- UI는 색/기호 외에 범위와 출처 배지를 함께 노출해야 함(§9 접근성과 정합).
- 입력 부담↑ → 에이전트가 기본값(범위+출처) 채우고 사람이 교정하는 흐름으로 완화.

## 열린 질문

- 여러 evidence를 종합해 범위를 재계산하는 집계식을 규칙으로 둘지, 사람 판단으로 둘지 → M3에서 실측 후 결정.
- **[해소됨] 평가 축별 rubric 내용.** 5개 축의 정의문 + 앵커 사다리(L0…L4) v0 초안을 [`assess-hypothesis` 스킬](../../.claude/skills/assess-hypothesis/SKILL.md)에 작성, H-001로 첫 calibration(CAL-001) 검증 완료. 앵커 정교화는 사례 축적으로 지속(D5·D6이 수치를 M3 실측으로 미룬 것과 동일 패턴)이며 D3 Accepted를 막지 않는다.
- **[지속] 앵커 calibration.** 채점 사례가 앵커와 어긋나면 스킬의 앵커 문구를 교정. judge-LLM 채점의 축간 일관성·재현성은 M3 실측으로 점검.

# ADR-D3 — Confidence 데이터 모델 + Provenance

- 상태: **Accepted** (구조·원칙 확정; 축별 앵커 문구는 v0 초안이며 사례 축적으로 calibration — D5·D6과 동일 패턴)
- 작성일: 2026-08-28 · 보완: 2026-10-10 (평가기준 리서치 반영 — 원칙 4·축 역할 구분 추가)
- 관련: PRODUCT-CONCEPT §4.3 §6.4 §20(가짜 정밀도) §21.10 · REVIEW 1-③ · rubric 운영: [`assess-hypothesis` 스킬](../../.claude/skills/assess-hypothesis/SKILL.md) · 근거 리서치: [평가 기준 공백(ACH·GRADE·LLM-judge)](../../reference/evaluation-criteria-gaps-research.md)

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
- **[원칙 4] 재채점 안정성 — 반박은 증거가 아니다 (sycophancy 차단):** 등급 변경은 **새 외부 독립 evidence가 추가되었을 때만** 허용한다. 사용자·에이전트의 반박 *텍스트*만으로는 변경 금지 — 반박은 의견이므로 원칙 2(`llm-opinion` 금지)의 재채점 버전이다. 재채점 시 이전 등급·`evidence_ref`를 함께 제시하고 "무엇이 바뀌었나"를 evidence로 답해야 한다. 근거: LLM은 반박받으면 외부 증거 변화 없이도 ~58% 확률로 답을 바꾸고 그중 상당수가 옳던 답을 악화시킨다(Sharma et al. 2024, [리서치 §3.4](../../reference/evaluation-criteria-gaps-research.md)). 반박 자체는 버리지 않고 해당 축 rationale의 *열린질문*으로 기록한다.
- **축 역할 구분 — 5축은 동질이 아니며 합산하지 않는다:**
  - **신뢰 축** `plausibility` · `evidence_strength` — "참인가"에 대한 상태. plausibility는 사전(prior), evidence_strength는 확보 근거(지지·반증 **균형** 반영 — 순수 반증 가중 금지, [리서치 §1.3](../../reference/evaluation-criteria-gaps-research.md)).
  - **포트폴리오 축** `novelty` · `impact` — "탐구할 가치"에 대한 상태. novelty는 중복·사고 포화 감지(§8), impact는 우선순위. 참/거짓과 무관하므로 신뢰 축과 절대 합산하지 않는다.
  - **다리 축** `testability` — 다음 행동 선정. `impact × testability`가 "다음에 실제로 돌릴 가설"을 고른다(CAL-002: impact만 보면 비전가설로 교착, testability와 교차해야 실행 가능 가설이 드러남).
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

- 여러 evidence를 종합해 범위를 재계산하는 집계식을 규칙으로 둘지, 사람 판단으로 둘지 → M3에서 실측 후 결정. [리서치 §2.3](../../reference/evaluation-criteria-gaps-research.md)에 따라 proper-score류 교정 기법은 "등급→경험적 정답률" 매핑 테이블 구축이 선행돼야 하므로(확률 전제), 집계는 신뢰 축에 한해서만 검토한다(축 역할 구분 참조).
- GRADE 5개 하향 도메인이 범위를 "몇 등급" 넓혀야 하는지의 임계 규칙 — v0 운용 규칙(도메인당 경계 1개, 최대 1등급)은 스킬에 두고 M3 사례로 교정.
- **[해소됨] 평가 축별 rubric 내용.** 5개 축의 정의문 + 앵커 사다리(L0…L4) v0 초안을 [`assess-hypothesis` 스킬](../../.claude/skills/assess-hypothesis/SKILL.md)에 작성, H-001로 첫 calibration(CAL-001) 검증 완료. 앵커 정교화는 사례 축적으로 지속(D5·D6이 수치를 M3 실측으로 미룬 것과 동일 패턴)이며 D3 Accepted를 막지 않는다.
- **[지속] 앵커 calibration.** 채점 사례가 앵커와 어긋나면 스킬의 앵커 문구를 교정. judge-LLM 채점의 축간 일관성·재현성은 M3 실측으로 점검.

---
name: assess-hypothesis
description: Inquiry 가설의 5개 평가 축(plausibility·evidence_strength·novelty·impact·testability)을 ADR-D3 앵커 사다리로 채점한다. 범위+source+provenance를 출력하고, 외부 독립 evidence만 인정한다. 가설을 평가·채점·scoring 하거나 confidence 범위를 매길 때 사용.
---

# assess-hypothesis — 가설 평가 rubric (v0 초안)

Inquiry의 가설 confidence를 [ADR-D3](../../../docs/decisions/ADR-D3-confidence-model.md)의 규칙대로 채점하는 살아있는 rubric.
**구조·원칙은 D3에 동결**되어 있고, 이 문서는 **축별 앵커 문구 + calibration 사례**를 담아 사례가 쌓이며 정교화된다.

> 상태: v0 초안. 앵커는 아래 "Calibration 사례"가 늘어남에 따라 교정된다(D5·D6이 수치를 M3 실측으로 미룬 것과 동일 패턴).

## 채점 원칙 (D3에서 동결)

1. **앵커 사다리 분류, 확률 추정 아님.** 각 축은 `[0~1]` 확률을 *추정*하지 말고, 관찰 가능한 기준을 만족하는 등급(L0…L4)을 **고른다**. 저장 숫자는 등급의 파생 라벨.
2. **범위 = 인접 등급 간 불확실성.** "L2는 확실, L3인지 애매" → `[0.5, 0.75]`. 아무 폭이나 긋지 않는다. 등급이 확실하면 범위는 좁다.
3. **evidence는 시스템 밖 독립 자료만.** 허용: `external-article` · `measured-result` · `human-interview` · `human-judgment` · `dataset`. **`llm-opinion` 금지**(순환). 판정: *LLM이 사라져도 남는 것만 evidence.*
4. **evidence_strength ↔ plausibility 분리.** 그럴듯함(mechanism)과 근거 강도(확보한 자료)는 절대 합치지 않는다. 근거 없이도 plausibility는 높을 수 있고, 그 반대도 가능.
5. **source 위계** `agent-estimate` < `human-judgment` < `measured-result`. agent-estimate는 제안일 뿐 자동 확정 금지.

## 채점 절차

1. 가설의 `claim`·`assumptions`·`falsified_if` 와 첨부된 evidence를 읽는다.
2. **evidence를 먼저 원칙 3으로 필터** — llm-opinion·근거 없는 것은 제외.
3. 각 축마다: 앵커 사다리에서 충족하는 최고 등급을 찾고, 인접 등급이 애매하면 범위로 표현.
4. 각 축 값에 그 판단의 근거가 된 `evidence_ref`를 남긴다.
5. 출력 형식(아래)으로 반환. source는 채점 주체에 맞게.

## 5단계 눈금 (전역)

`[0,1]`을 균등하게 5개 등급으로 나눈다. 각 등급의 *일반* 의미는 축과 무관하게 공통이고, 아래 축별 사다리는 이를 각 축에 특화한 것이다.

| 등급 | 범위 | 일반 의미 |
|---|---|---|
| **L0** | 0.0 – 0.2 | 없음 / 부재 / 성립 불가 |
| **L1** | 0.2 – 0.4 | 약함 / 일화적 / 주변부 |
| **L2** | 0.4 – 0.6 | 중간 / 혼재 / 부분적 |
| **L3** | 0.6 – 0.8 | 강함 / 명확 / 핵심 |
| **L4** | 0.8 – 1.0 | 결정적 / 필연 / 전면적 |

- 확신하는 단일 등급 → 범위 = 그 등급의 밴드 (예: 확실한 L2 = `[0.4, 0.6]`).
- 인접 등급 사이가 애매 → 경계를 걸치는 범위 (예: L2~L3 = `[0.5, 0.7]`).
- **범위 폭 = 불확실성의 크기.** 임의로 넓히지 않는다.

## 축별 앵커 사다리 (v0)

### plausibility — 주장의 mechanism이 얼마나 성립하는가 (근거 강도와 무관)
확보 evidence가 0이라 가정했을 때, 주장의 인과 mechanism 자체가 얼마나 성립하는가.
- **L0 (0.0–0.2)** 알려진 사실·제약과 모순. mechanism 성립 불가.
- **L1 (0.2–0.4)** 성립하려면 여러 무리한 가정이 동시에 참이어야 함.
- **L2 (0.4–0.6)** 그럴듯한 mechanism과 반대 mechanism이 비등.
- **L3 (0.6–0.8)** 명확한 인과 mechanism 존재. 반례는 특수 조건에서만.
- **L4 (0.8–1.0)** 확립된 원리에서 거의 필연적으로 도출. 반증하려면 알려진 법칙을 뒤집어야.

### evidence_strength — 확보한 근거가 얼마나 강한가 (그럴듯함과 무관)
- **L0 (0.0–0.2)** 근거 없음 / 추측.
- **L1 (0.2–0.4)** 일화적·간접 (포럼 불평, 단일 개인 의견).
- **L2 (0.4–0.6)** 복수의 독립된 1차 자료 (다수 인터뷰, 공개 데이터셋).
- **L3 (0.6–0.8)** 직접 관찰 / 파일럿 데이터.
- **L4 (0.8–1.0)** 통제된 실험 / 재현된 측정.

### novelty — 기존 그래프에 없던 새 관점·정보를 더하는가 (반복 감지)
- **L0 (0.0–0.2)** 기존 가설·근거의 중복 (새 근거·전제·연결 0).
- **L1 (0.2–0.4)** 기존 것의 사소한 재표현 (표현만 다름).
- **L2 (0.4–0.6)** 기존 축 위에 새 근거/전제 1개 추가.
- **L3 (0.6–0.8)** 기존에 없던 관점 또는 다른 가설과의 새 연결.
- **L4 (0.8–1.0)** 그래프에 새 영역을 여는 근본적으로 새로운 방향.

### impact — 참이면 Inquiry의 결정·방향에 얼마나 크게 작용하는가 (우선순위)
- **L0 (0.0–0.2)** 참이어도 어떤 결정도 안 바뀜.
- **L1 (0.2–0.4)** 주변부 세부만 영향.
- **L2 (0.4–0.6)** 한 갈래(sub-inquiry)의 방향을 바꿈.
- **L3 (0.6–0.8)** 핵심 결정 / 제품 방향을 바꿈.
- **L4 (0.8–1.0)** Inquiry 전체의 전제를 재정의 (go/no-go 급).

### testability — 지지/반증할 실험을 설계할 수 있는가 (falsified_if와 연결)
- **L0 (0.0–0.2)** 원리상 반증 불가. 검증 수단 없음.
- **L1 (0.2–0.4)** 검증하려면 비현실적 자원·시간 필요.
- **L2 (0.4–0.6)** 대리지표(proxy)로만 검증 가능. 직접 측정 어려움.
- **L3 (0.6–0.8)** 명확한 falsified_if + 현실적 실험 설계 가능.
- **L4 (0.8–1.0)** 즉시 실행 가능한 결정적 실험 존재 (짧은 시간에 명확한 지지/반증).

## 채점 근거 템플릿 (ADR 형식)

각 축 점수의 근거는 [ADR 템플릿](../../../docs/decisions/_TEMPLATE.md)과 **같은 뼈대**로 남긴다 — 채점도 하나의 결정이므로. 점수 규모에 맞춘 압축형으로 매핑한다:

| ADR 섹션 | 채점 근거에서 |
|---|---|
| 결정 | 고른 등급 (예: `L2`, 범위 `[0.4, 0.6]`) |
| 근거 | `evidence_ref` — 외부 독립 자료만 (원칙 3) |
| 대안 (기각) | 인접 등급을 왜 안 골랐나 (L1도 L3도 아닌 이유) |
| 열린 질문 | 무엇이 이 점수를 바꾸나 (= 이 점수의 falsified_if) |

- **맥락·트레이드오프**는 가설 수준에서 공유되므로 축 점수에선 보통 생략.
- 점수가 다투어지거나(`contested`) pivotal할 때만 전체 ADR 섹션으로 확장 → 실제로 `docs/decisions/`의 decision record가 될 수도 있다(도그푸딩).

## 출력 형식

```yaml
assessment:
  plausibility:      [low, high]
  evidence_strength: [low, high]
  novelty:           [low, high]
  impact:            [low, high]
  testability:       [low, high]
  source: agent-estimate   # | human-judgment | measured-result
  evidence:
    - {type: external-article, uri: "...", quote: "...", retrieved_at: "YYYY-MM-DD"}
  rationale:               # 축마다 ADR 뼈대(결정/근거/대안기각/열린질문)
    evidence_strength:
      결정: "L1 [0.25, 0.45]"
      근거: [ev-1]           # evidence_ref
      대안기각: "L2(독립 1차 자료 복수)는 인터뷰·데이터셋이 없어 미충족"
      열린질문: "파일럿 재사용률 측정이 나오면 L3로 이동"
```

## Calibration 사례

> 채점 예시가 여기 누적된다. 앵커가 사례와 어긋나면 앵커 문구를 고친다 — 이 섹션이 rubric의 정교화 엔진.

### CAL-001 · H-001 (멀티모달 Agent 디버거 수요)
- **가정한 evidence** (exploring 시작 시점): HN/포럼 스레드 3건("멀티모달 디버깅이 어렵다"), 작성자 직관. 인터뷰·측정 데이터 없음.
- **채점 (source: agent-estimate)**

| 축 | 범위 | 걸린 앵커 · 근거 |
|---|---|---|
| plausibility | [0.50, 0.70] | L2~L3 — "재현하면 디버깅 시간↓" mechanism은 명확하나 "기존 tracing으로 충분" 반대 mechanism도 성립 |
| evidence_strength | [0.25, 0.45] | L1 — 포럼 스레드 3건은 일화적. 독립 1차 자료(인터뷰·데이터셋) 없어 L2 미충족 |
| novelty | [0.60, 0.80] | L3 — tracing 도구는 있으나 "멀티모달 + 재현·비교" 조합은 기존에 없던 관점 |
| impact | [0.75, 0.90] | L3~L4 — "수요가 실재하는가"는 제품 핵심 전제. 참/거짓이 go/no-go를 가름 |
| testability | [0.55, 0.75] | L3 — falsified_if("한 번 쓰고 반복 안 함")가 명확, 프로토타입 재사용률로 검증 가능 |

- **evidence_strength 근거 (ADR 뼈대 예시):**
  - 결정: `L1 [0.25, 0.45]` (L1 확실, L2 경계 일부 걸침)
  - 근거: HN 스레드 3건 (`external-article`)
  - 대안기각: L2(복수 독립 1차 자료)는 인터뷰·데이터셋 부재로 미충족 / L0은 아님(관찰된 불평 존재)
  - 열린질문: 파일럿 재사용률(`measured-result`)이 붙으면 L3로 이동
- **관찰:** 원문 §6.4의 단일 점수(evidence_strength 0.30, plausibility 0.72)와 달리, **plausibility는 높고 evidence_strength는 낮은** 상태가 앵커로 명시적으로 드러남 → 원칙 4(분리)가 실제로 작동함을 확인. "그럴듯하지만 아직 근거는 약하다" = exploring을 더 돌려 measured-result를 모아야 한다는 신호.

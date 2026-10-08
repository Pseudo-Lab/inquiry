# 평가 기준 공백(Layer 3) 리서치 보고서 — ACH·Calibration·LLM-judge 편향

2026-10-08. [평가 기준 정리](#) Layer 3에서 "아직 근거 없음"으로 남겼던 3개 공백을 deep-research로 조사. 5각도 · 23출처 fetch · 98주장 추출 · **25주장 검증(24확증 / 1기각)**. 선행: [분기 방법론 리서치](logical-branching-methodology-research.md) · [LLM 과잉수긍 종합](llm-sycophancy-and-probabilistic-decision.md)(§3.4 sycophancy 근거) · 대상 설계: [ADR-D3 confidence 모델](../docs/decisions/ADR-D3-confidence-model.md) · [assess-hypothesis 스킬](../.claude/skills/assess-hypothesis/SKILL.md).

> ⚠️ **핵심 반전:** 세 공백 모두 "확립된 방법론으로 채울 수 있다"지만, **각 방법론이 중대한 경험적 한계를 동반**한다. 특히 (1) ACH의 반증 채점은 효과가 **입증되지 않았고** 순수 반증은 역편향을 부르며, (3) LLM 과신 증거는 오히려 **ADR-D3의 현재 선택(확률 대신 앵커 등급)을 정당화**한다. 즉 이 리서치는 "새 기능을 추가하라"가 아니라 **"현 설계가 옳고, 어디를 조심스럽게 보강할지"**를 알려준다.

---

## 1. ACH와 반증 지향 채점 — "도입하되 순수 반증은 금물"

### 1.1 ACH의 정체: 반증 지향 설계 (서술적 사실, 논란 없음)
**출처:** Dhami, Belton & Mandel (2019). *The Analysis of Competing Hypotheses in Intelligence Analysis.* Applied Cognitive Psychology. [doi:10.1002/acp.3550](https://onlinelibrary.wiley.com/doi/full/10.1002/acp.3550) · [PDF](https://strathprints.strath.ac.uk/69049/1/Dhami_etal_ACP_2019_The_analysis_of_competing_hypotheses_in_intelligence.pdf). 원형: Heuer (1999) *Psychology of Intelligence Analysis*.

ACH는 (a) 대안 가설 열거 → (b) 증거를 각 가설에 **불일치(inconsistent)**로 평정 → (c) 증거의 **진단성(diagnosticity)·신뢰성**으로 믿음 조정 → (d) **가장 적은 불일치 증거를 가진 가설** 선택 → (e) 미래에 반증할 지표 식별. 확증이 아니라 **반증과 진단성**으로 거른다.

**Inquiry 대응:** `evidence_strength` 축과 "가설×증거 행렬" 개념의 이론적 기반. `llm-opinion 금지`는 ACH의 "외부 진단적 증거 우선"과 정합.

### 1.2 그런데 ACH는 효과가 입증되지 않았다 (경험적 경고)
- **확증편향을 안정적으로 못 줄임:** Dhami et al.(2019) 무작위 실험(분석가 50명) — "ACH의 확증편향 감소에 **혼재된 증거**, 오히려 **판단 비일관성·오류를 늘릴 수 있음**." 최종 결론이 행렬과 일치한 비율 ACH군 64% vs 미훈련군 100%.
- **효과는 비전문가에 국한:** MITRE MTR-04B0000017 (Cheikes et al. 2004) — "ACH는 확증편향을 줄였으나 **전문 분석 경험 없는 참가자에만**, 숙련 분석가엔 효과 없음."
- **셀 채점 기준이 모호:** "무엇이 일치/불일치인지 기준 불명확 → 판단 과정을 신뢰 불가."
- **편향의 소재는 '가중'이지 '해석'이 아님:** MITRE — 분석가는 증거가 확증/반증인지 **분류는 믿음에 영향 안 받았으나, 확증 증거에 더 큰 가중**을 줬다(weighting bias).

### 1.3 순수 반증은 역편향(disconfirmation bias)을 부른다
**출처:** Dhami et al. (2024). *Cognitive Research: Principles and Implications.* [doi:10.1186/s41235-024-00560-y](https://link.springer.com/article/10.1186/s41235-024-00560-y). Mandel & Wilcox (2024).

"가설을 반증하는 데 집중함으로써 분석가는 **실제로 거짓인 가설을 선택**하게 만드는 disconfirmation bias를 보일 수 있다"(Mandel 2020). ACH가 Popper를 **오용**해 불일치 평정에만 비영(非零) 가중을 주는 것은 "동등하게 강한 역편향"을 낳을 수 있다.

### 1.4 행렬 **방향**이 통계적으로 유의하다
Dhami et al.(2024): **가설=행, 증거=열** 배치는 확증편향을 유의하게 줄였으나(χ²(2)=9.43, p=0.009, φ=0.24; 60.8%가 비확증 가설 선택), **전통적 ACH 배치(가설=열)는 효과 없음.** (표본 소규모, 효과 중간.)

### ✅ ACH → Inquiry 권고
1. `evidence_strength`를 **순수 반증 축으로 설계하지 말 것** — "반증 증거에 가중하되 지지 증거도 베이즈적으로 반영"하는 **균형 축**. 순수 반증 L4 앵커 금지.
2. 앵커 사다리의 **"일치/불일치" 기준을 구체적 예시로 명시**(ACH 모호성 결함 교정). LLM 심판에 모호한 기준을 주면 신뢰도 하락.
3. `plausibility` **사전(prior)을 명시적으로 추적** — 단순 불일치 카운팅(비베이즈) 금지.
4. 편향 소재가 '가중'이므로, **각 증거의 가중(신뢰성·진단성)을 외부 근거로 고정**(llm-opinion 금지)하면 직접 효과.
5. 가설×증거를 제시할 때 **가설=행 방향** 레이아웃 권고.

---

## 2. Calibration·집계 — GRADE가 ADR-D3와 정합, 집계는 공백 유지

### 2.1 GRADE: 이산 등급 + "범위에 대한 신뢰" (ADR-D3와 철학적 정합)
**출처:** [CDC/ACIP GRADE Handbook Ch.7](https://www.cdc.gov/acip-grade-handbook/hcp/chapter-7-grade-criteria-determining-certainty-of-evidence/index.html) · Hultcrantz et al. (2017) J Clin Epidemiol [PMID 28529184](https://www.jclinepi.com/article/S0895-4356(16)30703-X/fulltext).

GRADE는 확실성을 **4개 이산 등급(High/Moderate/Low/Very Low)**으로, 각 등급을 **점 확률이 아니라 "참 효과가 추정치에 얼마나 가까운지에 대한 신뢰"**의 질적 진술로 표현. 2017년 "참 효과가 **임계값 한쪽 또는 범위 내**에 있을 신뢰"로 개념 전환.

→ **ADR-D3의 "L0~L4 앵커 등급 + 범위=불확실성·확률 아님"과 직접 정합.** (단 ⚠️ 2-1 투표: GRADE의 범위는 *효과 크기* 범위, ADR-D3의 범위는 *질적 등급* 범위 — 유비이지 동형 아님.)

### 2.2 GRADE 5개 하향 도메인 → confidence 범위 확장 트리거
risk of bias · inconsistency · indirectness · imprecision · publication bias. **Inquiry 보완:** 각 증거 채점 후 이 5개를 점검해 confidence 범위를 인접 등급으로 **넓히는 규칙**으로 조작화 가능(예: 증거 간 inconsistency 있으면 L3→L3~L2로 확장).

### 2.3 Calibration 측정·분해의 수학적 기반
- **CORP/isotonic reliability diagram** — Dimitriadis, Gneiting & Jordan (2021) PNAS [arXiv:2008.03033](https://arxiv.org/pdf/2008.03033): 전통적 binning은 빈 개수(m=9/10/11)만 바꿔도 결과가 요동쳐 **신뢰 불가**; CORP는 isotonic regression(PAV)으로 재현 가능한 다이어그램 + 단일 miscalibration 측정(MCB) 제공.
- **Proper score 분해** — Bröcker (2008) [arXiv:0806.0813](https://arxiv.org/pdf/0806.0813): 기대 점수를 **uncertainty·resolution·reliability** 3항으로 분해(Brier 일반화).
- ⚠️ **기각된 주장:** "reliability·resolution이 점수에 단조(monotone) 효과" → **0-3 기각**. "교정 개선이 항상 점수 개선"이라 가정 금지.

### ✅ Calibration → Inquiry 권고
1. ADR-D3의 이산 앵커 + 범위 설계는 GRADE와 정합하므로 **유지**.
2. GRADE 5개 하향 도메인을 **"범위 확장 트리거"**로 assess-hypothesis에 도입.
3. **집계 함수는 여전히 공백:** 5축 → 하나의 교정된 범위로 합치는 구체 함수 미정. proper-score 분해(uncertainty/resolution/reliability)를 쓰려면 **"등급→경험적 정답률" 매핑 테이블을 먼저 구축**해야 함(확률 전제 방법이라 이산 등급에 직접 적용 불가). → M3 실측 축적 후 결정(ADR-D3가 수치를 M3로 미룬 것과 동일).

---

## 3. LLM-as-judge 편향 — 현 설계를 **정당화**하되 보강 필요

### 3.1 프런티어 LLM은 "교정하라"는 지시에도 체계적으로 과신
**출처:** KalshiBench (Nel, 2025) [arXiv:2512.16030](https://arxiv.org/pdf/2512.16030). 5개 모델(Claude Opus 4.5, GPT-5.2-XHigh 등) 전부 **ECE 0.120~0.395**. 90%+ 자기신뢰 구간에서 15~32% 틀림(예: Opus 4.5가 94.6% 확신 주장 → 실제 70.0% 정확). "miscalibration은 지침 부재가 아니라 **지시 미준수**."

### 3.2 확장 추론이 교정을 **악화**시킨다
같은 벤치마크: 가장 긴 추론(~2M 토큰)의 GPT-5.2-XHigh가 **최악 교정(ECE=0.395)**. 원인 추정 — **"확장 추론 내 확증편향": 긴 추론 사슬이 증거로 갱신하기보다 초기 가설을 강화**하고 정확도 향상 없이 신뢰만 올림.

### 3.3 언어화 신뢰는 miscalibrated이나 프롬프트 기법이 좌우
**출처:** Yang, Tsai & Yamada (2024) [arXiv:2412.14737]; Tian et al. (2023, EMNLP "Just Ask for Calibration"). 언어화 신뢰는 과신 경향이나, **구조화된 confidence-elicitation 프롬프트**가 교정을 측정 가능하게 개선(ECE ~50%↓). 복수 후보 동시 제시 후 채점도 개선.

### 3.4 Sycophancy — 반박 시 채점을 뒤집는 편향 (Inquiry에 가장 치명적)
**출처:** 프로젝트 초기 리서치 [LLM 과잉수긍·확률적 의사결정 종합](llm-sycophancy-and-probabilistic-decision.md) (2026-09-08) · 원출처: Sharma et al. (2024, ICLR) *Towards Understanding Sycophancy in Language Models* [arXiv:2310.13548].

과신(§3.1)·확장추론(§3.2)과 **별개의** 편향: LLM은 사용자가 반박하면 **정확성보다 동의를 우선**해 답을 바꾼다. 실측 — 반박 시 **~58%** 확률로 답 변경, 그중 **14.66%는 맞던 답을 틀리게**(regressive) 뒤집음. RLHF가 선호 분포를 "반박받으면 수긍" 쪽으로 기울인 결과이며, 내부에 **선형 분리 가능한 feature**로 존재.

**Inquiry에서 왜 치명적:** 사용자가 가설 채점에 "이건 틀린 것 같은데?"라고 하면, agent가 **외부 증거 변화 없이도** 약 58% 확률로 채점을 뒤집고 그중 절반 가까이가 **옳던 채점을 악화**시킬 수 있다. 과신이 "처음부터 자신함"이라면, sycophancy는 "**사후 반박에 무너짐**" — 채점의 *안정성*을 직접 위협한다.

### ✅ LLM-judge → Inquiry 권고
1. **현 설계가 정당화됨:** agent-estimate를 raw 확률로 받지 않고 **외부 증거에 앵커된 이산 등급**으로 강제하는 ADR-D3 선택이 과신 문헌에 의해 직접 뒷받침됨. `llm-opinion 금지`는 self-preference/self-enhancement bias의 주 경로(모델이 자기 생성 내용 선호) 차단.
2. **형제 가설 동시 채점**(CAL-002)이 reference-guided·상대비교로 **단일 가설 확증(§3.2 경고)을 억제** — 유지·강화.
3. **그러나 부족분:**
   - **확장 추론 경계:** agent가 긴 추론으로 가설을 self-score하면 **초기 가설 확증 위험** → 긴 CoT에 의존한 자기채점 지양.
   - **position bias:** 형제 가설 제시 **순서 스왑/무작위화** 필요(미도입).
   - **잔여 과신:** **다중 심판 패널(multi-judge, PoLL류)**로 완화(비용 대비 효과는 열린 질문).
   - 채점 프롬프트를 **구조화 앵커 루브릭 + 외부 증거 참조** 형식으로 표준화.
   - **sycophancy(§3.4) 차단:** 사용자 반박만으로 채점을 바꾸지 말 것 — **새 외부 독립 증거가 있을 때만** 등급 변경을 허용하는 규칙을 assess-hypothesis에 명시(`llm-opinion 금지`의 반박 버전). 재채점 시 이전 등급·evidence_ref를 보여주고 "무엇이 바뀌었나"를 증거로 요구.

---

## Inquiry 설계 보완 요약 (이 리서치의 실행 항목)

| 대상 | 현 상태 | 리서치 기반 보완 | 우선 |
|---|---|---|---|
| `evidence_strength` 앵커 | L0~L4 | **균형 축 유지**(순수 반증 금지), 일치/불일치 기준 구체 예시 | 중 |
| `plausibility` | 앵커 등급 | **사전(prior)으로 명시 추적**(베이즈 구조 보존) | 중 |
| confidence 범위 | "인접 등급 불확실성" | GRADE **5개 하향 도메인을 범위 확장 트리거**로 | 중 |
| 5축 집계 | 미정 | **공백 유지** — 등급→정답률 매핑 선행, M3 실측 후 | 낮(M3) |
| agent-estimate 신뢰성 | 앵커+외부증거+형제채점 | **정당화됨** + position 스왑·다중심판·긴CoT 자기채점 지양 | 중 |
| **재채점 안정성(sycophancy)** | 규칙 없음 | 반박만으로 등급 변경 금지 — **새 외부 증거 있을 때만** 변경(§3.4) | **중상** |
| 채점 UI/프롬프트 | — | 가설=행 레이아웃, 구조화 앵커 프롬프트 | 낮 |

**결론:** ADR-D3의 핵심 선택 3가지 — ① 확률 추정 대신 **앵커 등급**, ② **범위=불확실성**, ③ **외부 독립 증거만** — 은 이번 리서치로 **강하게 정당화**됐다(GRADE 정합 + LLM 과신 경고). 추가할 것은 새 패러다임이 아니라 **조심스러운 보강**(균형 축·GRADE 트리거·편향 완화 장치)이며, **5축 집계 함수만 진짜 공백으로 남아 M3 실측까지 미룬다.**

---

## 주의·한계

1. **ACH 효과성 증거는 소표본**(분석가 50명, HypRow n=51, φ=0.24). "ACH는 효과 없다"가 아니라 "**통제 실험들이 편향완화 효과를 일관되게 입증하지 못했다**". 반증 지향 *설계*(서술적 사실)는 논란 없음.
2. **KalshiBench는 단일저자 비심사 preprint**, Claude 90-100% 구간 N=20, 도메인이 예측시장(가설 채점과 다름). 과신 *방향성*은 다수 독립 문헌과 일치해 견고하나 **구체 ECE 수치의 Inquiry 전이성은 제한적**.
3. **GRADE↔ADR-D3 정합 주장은 2-1 분할투표** — 범위 기반·비점확률 철학은 정합하나 구조적 동형은 아님.
4. **CORP/proper-score는 확률 예측 전제** — 이산 앵커에 직접 적용하려면 등급→정답률 매핑 선행.
5. 일부 PDF(Wiley/MITRE/jclinepi) HTTP 403 — 독립 검색 스니펫·미러로 교차검증, 핵심 인용은 다출처 축자 재현.

## 열린 질문 (M3/후속)

1. 5축을 하나의 교정된 범위로 집계하는 **구체 함수** + 등급→정답률 보정 테이블 경험적 구축법.
2. 다중 심판/위치 스왑의 **비용 대비 교정 개선** — 외부증거전용이 이미 self-preference를 막은 상태에서 한계이익.
3. ACH 행렬 방향 효과(가설=행)가 **인간이 아닌 LLM 채점 주체**에도 성립하는가(직접 실험 필요).
4. GRADE 5개 도메인이 confidence 범위를 **"몇 등급" 넓혀야** 하는지 임계 규칙.

---

*집계: 5각도 · 23출처 · 98주장 추출 · 25검증(24확증/1기각) · 105 에이전트 호출. 재현: deep-research 하네스, 비결정적.*

# 연구용 "사고 분기(경쟁 가설 설계)"와 "추론 품질 채점"의 방법론적 토대 — 리서치 보고서

2026-10-08. 작성 방식: deep-research 하네스(5각도 병렬 검색 → 24개 출처 수집 → 108개 주장 추출 → 25개 상위 주장 3표 적대적 검증 → 종합). **25개 주장 중 25개 확증, 0개 폐기.** 평가 대상이 아닌 "무엇을 말하는 논문인가" 수준의 서술적 귀속이 대부분이라 확증률이 높다.

> 목적: 로컬 탐구 도구 **Inquiry**의 설계 — 하나의 질문을 **DAG 형태의 경쟁 가설**로 분기하고, 각 가설을 **5개 축(plausibility·evidence_strength·novelty·impact·testability)**으로 채점 — 를 기존 연구방법론에 근거 짓는다.

---

## TL;DR

Inquiry의 "질문 → 경쟁 가설 DAG → 다축 채점" 설계는 **임의 발상이 아니라 130년 된 과학방법론 계보에 직접 근거 짓을 수 있다.**

- **분기의 기원**: Chamberlin(1890/1897)의 *다중 작업 가설법*이 "여러 경쟁 가설을 병렬 유지해 확증편향을 중화"한다는 원리를 제공 → Inquiry가 단일 답이 아닌 경쟁 가설 DAG를 쓰는 **원리적 정당화**.
- **분기 후 절차**: Platt(1964) *strong inference*가 이를 반증 지향 3단계로, Yanco et al.(2020)이 데이터 수집 전 구조화·평가 5단계로 공정화.
- **생성과 평가의 분리**: Yu & Zenker(2018)의 Peirce 귀추법 해석이 "가설 **생성**(abduction) ≠ 가설 **평가**(IBE)"를 논증 → Inquiry의 **분기 단계와 채점 단계 분리**를 철학적으로 뒷받침하고, `testability`·`plausibility`를 평가 축으로 쓰는 직접 근거.
- **구조 vs 내용**: Toulmin 모델의 ML 구현(Mirzababaei & Pammer-Schindler 2021)은 "구조 요소 탐지 ≠ 내용적 타당성 평가"라는 **자동 채점의 한계선**을 경고.
- **LLM 시대 선례**: Tree of Thoughts, Graph of Thoughts, HypoAgents, ChemReasoner/AI Co-Scientist가 각각 분기 탐색·DAG 집계·베이지안 다축 채점·토너먼트 순위화를 구현 → Inquiry의 **DAG + 다축 채점의 직접 선례**.

⚠️ **단, 요청 항목 중 ACH·Popper·IBIS·issue tree/MECE·GRADE·Brier/calibration·LLM-as-judge 일반 연구는 이번 패스에서 직접 검증되지 않았다**(§5 공백). 이 보고서의 근거로 삼지 말고 2차 리서치가 필요하다.

---

## (A) 가설 분기·설계 방법론

### A1. Chamberlin — 다중 작업 가설법 (경쟁 가설 분기의 기원)
**출처:** Chamberlin, T. C. *The Method of Multiple Working Hypotheses.* Science (1890); 재판 J. of Geology (1897). [원문 PDF](https://www.mantleplumes.org/WebDocuments/Chamberlin1897.pdf) · [McGill 미러](https://www.eps.mcgill.ca/~courses/c590/Chamberlain%201897.pdf)

탐구를 세 역사적 단계로 본다 — *지배이론법(ruling theory) → 단일 작업가설법(working hypothesis) → 다중 작업가설법(multiple working hypotheses)* — 그리고 세 번째를 우월한 교정책으로 제시한다. 핵심 메커니즘은 **처음부터 모든 합리적 설명을 병렬로 전개**하여 연구자의 노력과 "애정(affection)"을 모든 가설에 공평히 분산함으로써, 단일 가설이 유발하는 무의식적 선택적 주의(확증 사실 과장 + 반증 사실 방치)를 중화하는 것이다.

> *"The investigator thus becomes the parent of a family of hypotheses; and ... is morally forbidden to fasten his affections unduly upon any one."*
> *"There is an unconscious selection and magnifying of the phenomena that fall into harmony with the theory ... and an unconscious neglect of those that fail of coincidence."*

**Inquiry 대응:** 하나의 질문을 여러 경쟁 가설로 분기하는 설계의 **직접적 학술 기원**. "병렬 유지로 편향 중화"가 DAG-of-hypotheses의 원리적 정당화이자, Framing이 생성하는 가설 후보를 "서로 성격이 다르게" 만드는 M1a 기준의 근거.

### A2. Chamberlin — 공조 원인(coordinate causes)과 다원인 종합
**출처:** 위와 동일(Chamberlin 1897).

복잡한 현상은 대개 단일 원인이 아니라 **다수의 공조 원인**을 가지므로 원인들의 조율이 필요하며, 단일 가설법은 이를 포착하기에 "무능(incompetent)"하다고 논증한다(5대호 분지 = 선행 하천 계곡 + 빙하 굴식 + 지각 변형의 공동 산물 예시).

**Inquiry 대응:** DAG가 **배타적 경쟁 가설뿐 아니라 "공조·부분 기여" 가설**도 담아야 함을 시사. 즉 단순 승자독식 채점이 아니라 **다원인 종합(synthesize 연산)**을 설계에 반영할 근거.

### A3. Platt — Strong Inference (반증 지향 3단계)
**출처:** Platt, J. R. *Strong Inference.* Science (1964). 리뷰: [*Fifty years of J. R. Platt's strong inference*, J. Exp. Biol. (2014)](https://journals.biologists.com/jeb/article/217/8/1202/13095/).

Chamberlin의 다중 가설법을 계승한 3단계 반복 절차: **(1) 대안 가설 고안 → (2) 하나 이상을 배제하는 결정적 실험 설계 → (3) 실험 수행으로 깨끗한 결과 획득**, 이후 재귀적으로 하위·연속 가설로 정제.

**Inquiry 대응:** 가설 분기 후 "어느 가설을 **배제/확증**하는 증거인가"를 평가하는 반증 지향 채점의 방법론적 선례 — 특히 `testability`·`evidence_strength` 축. challenge 연산이 "반박 + check(측정법)"를 생성하는 것과 직접 대응.

### A4. Yanco et al. — 데이터 수집 전 가설 구조화 5단계
**출처:** Yanco, E. et al. (2020). *Dependency ... pre-data hypothesis vetting.* Royal Society Open Science. [doi:10.1098/rsos.200231](https://royalsocietypublishing.org/doi/10.1098/rsos.200231)

데이터 수집 **전에** 경쟁 가설을 구조화·평가하는 현대 5단계 반복 워크플로: 후보 가설 명세 → 가설별 모델 작성 → 시뮬레이션 표본분포 생성 → **분포 내 분산과 분포 간 중첩 정량화** → 수정 후 반복.

**Inquiry 대응:** Chamberlin의 철학을 "**분포 중첩 기반 구별가능성 정량화**"라는 조작적 채점으로 번역한 사례. 가설 간 **식별가능성/구별도**를 채점 축에 반영할 근거(현재 5축에 없는 보완 후보).

### A5. Yu & Zenker — 귀추법: 생성 ≠ 평가의 분리
**출처:** Yu, S. & Zenker, F. (2018). *Peirce knew why abduction is not IBE.* Argumentation 32. [doi:10.1007/s10503-017-9443-9](https://link.springer.com/article/10.1007/s10503-017-9443-9)

Peirce 의미에서 추론의 **"가설 생성" 측면만이 본래적 abduction**이고 "가설 평가·선택"은 IBE(최선의 설명으로의 추론)에 속하며, 둘을 별개 범주로 유지하라고 논증. 또한 가능 가설 집합(무한)의 유계 부분집합인 **"타당(plausible) 가설 집합"**을 정의하고 "연구 경제성(economy of research)"으로 검정 순서를 매겨 덜 타당한 것을 배제한다. Peirce의 좋은 가설 기준은 **"실험적 검증 가능성(testability)"과 "단순 가능성을 넘어선 plausibility"**.

**Inquiry 대응:** (1) **분기(생성) 단계와 5축 채점(평가) 단계의 분리**를 철학적으로 정당화, (2) `plausibility`로 DAG를 1차 필터링한 뒤 심층 증거 채점하는 2단계 로직의 근거, (3) `testability`·`plausibility`를 평가 축으로 쓰는 **직접 근거**.

### A6. LLM 시대의 사고 분기 — ToT / GoT / 과학 에이전트
**Tree of Thoughts** — Yao, S. et al. (2023). [arXiv:2305.10601](https://arxiv.org/abs/2305.10601). 추론을 여러 경쟁적 중간 "생각" 상태로 분기해 **트리로 탐색**하고 각 상태를 **LLM 자기평가(value/vote)로 채점·가지치기**. *단, 엄밀히 트리이고 thought는 경쟁 "가설"이 아닌 중간 단계 — Inquiry와는 구조적 유비이지 동치 아님.*

**Graph of Thoughts** — Besta, M. et al. (2024, AAAI). [논문](https://www.researchgate.net/publication/379296666). LLM 추론을 **임의 그래프(DAG 포함)**로 모델링해, 트리가 못 하는 **분기의 집계·종합(aggregation)**과 **정제·증류(distillation)**를 가능케 함(트리는 in-degree>1 불가, GoT는 가능).
→ **Inquiry가 트리가 아닌 DAG를 택한 것의 직접 정당화**이자, 경쟁 가설을 종합해 상위 결론으로 증류하는 synthesize 설계의 선례.

**과학 에이전트** — 서베이 [arXiv:2503.24047](https://arxiv.org/html/2503.24047v1). ChemReasoner(Sprueill et al., ICML 2024)는 각 노드가 별개 가설인 **계층적 탐색 트리를 MCTS로 탐색**; AI Co-Scientist(Nature)는 **multi-agent debate로 병렬 가설 평가·조기 폐기 + Elo 토너먼트 순위화**.
→ 분기 + 채점 + 경쟁적 순위화가 실제 과학 에이전트에서 작동한다는 증거.

---

## (B) 추론 품질 평가·채점법

### B1. Toulmin 논증 모델 — 구조 평가의 선례이자 한계선
**출처:** Mirzababaei, B. & Pammer-Schindler, V. (2021). Frontiers in AI. [PMC8680349](https://pmc.ncbi.nlm.nih.gov/articles/PMC8680349/)

대화형 에이전트가 ML 분류기로 Toulmin 3요소(**claim / warrant / evidence(ground)**)를 탐지해 논증 구조를 조작화할 수 있으나, **구조 요소의 존재 탐지만으로는 "내용적 타당성(content-wise plausibility)"을 평가할 수 없다.**

> *"identification of structural components does not per se allow us to assess content-wise plausibility of the made argument."*

**Inquiry 대응(⚠️ 가장 중요한 경고):** 가설 채점을 **"구조 충족도"와 "내용적 설득력"으로 분리**해야 한다. 5축 중 `plausibility`·`evidence_strength`는 구조 탐지로 환원되지 않는 **실질 판단**이며, 이것이 자동(LLM) 채점이 과신하기 쉬운 지점이다 — 이번 [모델 품질 평가](m2-model-quality-eval.md)에서 "평가 주체가 에이전트"라는 한계를 명시한 것과 정확히 같은 경계.

### B2. HypoAgents — 다축 사전 점수 + 베이지안 사후 갱신 + 엔트로피 기반 심화
**출처:** Duan, Y. et al. (2025). *HypoAgents.* [arXiv:2508.01746](https://arxiv.org/pdf/2508.01746)

생성된 가설에 **복합 다축 점수(novelty-relevance-feasibility, N-R-F)**로 사전 신념을 설정 → RAG로 외부 문헌 증거 수집 → **베이즈 정리로 사후 확률 갱신** → **섀넌 엔트로피 H=-Σp·log p**로 고불확실성 가설을 식별해 그 가지만 선택적으로 정제.

**Inquiry 대응:** **다축 가설 품질 채점 + 증거 기반 사후 채점**의 최신 직접 선례. N-R-F의 novelty는 Inquiry 5축의 `novelty`와 대응하고, evidence는 별도 likelihood 단계로 처리 → Inquiry의 `evidence_strength`를 **베이지안으로 조작화**할 설계 힌트. 또한 "불확실한 가지를 우선 심화"가 deepen 연산의 탐색 전략 근거.

### B3. testability·plausibility를 평가 축으로 (재인용)
Yu & Zenker(2018, §A5)가 Peirce 기준으로 **testability와 plausibility**를 좋은 가설의 평가 축으로 명시 → Inquiry 5축 중 2개의 **직접적 철학 근거**.

---

## Inquiry 설계 ↔ 방법론 대응 요약

| Inquiry 설계 요소 | 근거 방법론 | 비고 |
|---|---|---|
| 질문 → **경쟁 가설 분기** | Chamberlin 1890/1897 (A1) | 편향 중화가 원리 |
| **DAG**(트리 아님) | Graph of Thoughts (A6) | in-degree>1 집계·종합 가능 |
| **synthesize**(다원인 종합) | Chamberlin 공조 원인 (A2), GoT distillation (A6) | 승자독식 아님 |
| **분기/채점 단계 분리** | Yu & Zenker 2018 (A5) | 생성(abduction)≠평가(IBE) |
| `testability` 축 | Platt 1964 (A3), Peirce (A5) | 반증 지향 |
| `plausibility` 축 | Peirce (A5) | 1차 필터 |
| `novelty` 축 | HypoAgents N-R-F (B2) | 다축 사전 점수 |
| `evidence_strength` 축 | Platt (A3), HypoAgents 베이즈 (B2) | 사후 갱신으로 조작화 가능 |
| challenge(반박+check) | Platt strong inference (A3) | 결정적 실험 설계 |
| **채점 주체가 에이전트인 한계** | Toulmin ML (B1) | 구조≠내용 경계 |
| (보완 후보) 가설 간 구별가능성 | Yanco et al. 2020 (A4) | 현재 5축에 없음 |

---

## 공백 — 요청했으나 이번 패스에서 검증 안 된 항목 (근거로 쓰지 말 것)

연구 질문이 명시적으로 요구했으나 25개 검증 세트에 **직접 증거가 없어 미검증**인 항목(예산 소진·검색 각도 배분 탓):

- **(A)축:** ACH(Heuer, *Analysis of Competing Hypotheses*), **Popper 반증주의**, **IBIS / dialogue mapping / argument mapping**(Rittel & Kunz), **issue tree · MECE**(McKinsey 계보)
- **(B)축:** **GRADE** evidence grading, **Brier score / calibration**, Bayesian confidence 일반 이론, critical thinking 평가 척도(California Critical Thinking, Watson-Glaser), argument quality rubric, **LLM-as-judge** 일반 연구(G-Eval, MT-Bench 등)

이들은 특히 Inquiry의 ADR-D3(confidence 루브릭·calibration)와 직결되므로 **2차 리서치 1회를 권장**한다.

## 추가 주의

1. **유비 ≠ 동일성:** ToT는 트리이고 thought는 중간 단계(경쟁 가설 아님); HypoAgents N-R-F 3축은 Inquiry 5축과 novelty만 깔끔히 대응. "선례"는 구조적 유비.
2. **출처 품질:** LLM 흐름(HypoAgents, ChemReasoner 서베이, GoT 미러)은 arXiv 프리프린트·서베이 비중이 높아 peer-review 강도가 Chamberlin/Platt/Yanco 등 1차 저널보다 낮다. 단 claim이 "논문이 무엇을 하는가"의 서술이라 지위 약화 영향은 작다.
3. **시간 민감성:** LLM 분기·채점(2023–2025)은 급변 영역 — 후속 연구로 빠르게 보강될 수 있다.
4. **"Inquiry 대응" 서술은 본 합성의 적용 추론**이며 논문 저자의 직접 주장이 아니다.

## 열린 질문 (다음 리서치/설계 논의용)

1. ACH의 "반증 중심 행렬 채점"과 Inquiry 5축은 어떻게 대응/보완되는가? `evidence_strength`가 ACH식 반증 지향성을 반영하는가?
2. calibration(Brier)·Bayesian confidence를 Inquiry의 confidence 범위 산출(ADR-D3)에 어떻게 연결하고 GRADE식 grading과 정합시킬 것인가?
3. LLM-as-judge의 알려진 편향(위치·자기선호·장황함 선호)이 가설별 채점 신뢰성을 얼마나 위협하며, 완화책(앵커 사다리·다중 심판·구조-내용 분리 채점)은?
4. issue tree/MECE와 Toulmin 구조가 Inquiry DAG 노드/간선 스키마(상호배타성·망라성·의존관계)에 어떻게 매핑되는가?

---

## 출처 (검증에 사용된 1차·2차)

**1차(primary):**
- Chamberlin 1890/1897 — [mantleplumes.org](https://www.mantleplumes.org/WebDocuments/Chamberlin1897.pdf), [McGill](https://www.eps.mcgill.ca/~courses/c590/Chamberlain%201897.pdf)
- Platt strong inference 리뷰 — [JEB 2014](https://journals.biologists.com/jeb/article/217/8/1202/13095/)
- Yanco et al. 2020 — [RSOS](https://royalsocietypublishing.org/doi/10.1098/rsos.200231)
- Yu & Zenker 2018 — [Springer](https://link.springer.com/article/10.1007/s10503-017-9443-9)
- Mirzababaei & Pammer-Schindler 2021 — [PMC8680349](https://pmc.ncbi.nlm.nih.gov/articles/PMC8680349/)
- Tree of Thoughts — [arXiv:2305.10601](https://arxiv.org/abs/2305.10601)
- Graph of Thoughts — [ResearchGate](https://www.researchgate.net/publication/379296666)
- HypoAgents — [arXiv:2508.01746](https://arxiv.org/pdf/2508.01746)
- 과학 에이전트 서베이(ChemReasoner/AI Co-Scientist) — [arXiv:2503.24047](https://arxiv.org/html/2503.24047v1)

**미사용·미검증이나 수집된 참고(2차/블로그, §공백 관련):** ACH([Wikipedia](https://en.wikipedia.org/wiki/Analysis_of_competing_hypotheses)), Issue tree([Wikipedia](https://en.wikipedia.org/wiki/Issue_tree)), Falsifiability([Wikipedia](https://en.wikipedia.org/wiki/Falsifiability)), GRADE([핸드북](https://gradepro.org/handbook/)) — 이번 패스에서 claim 검증에 쓰이지 않았으므로 근거가 아닌 **다음 리서치 출발점**으로만 참고.

---

*집계: 5각도 · 24출처 fetch · 108주장 추출 · 25주장 검증(25확증/0폐기) · 106 에이전트 호출. 재현: deep-research 하네스, 비결정적.*

# ADR-D11 — 사고 포화·중복 감지 (휴리스틱 v0)

- 상태: **Accepted** (M3 구현과 함께 확정; 휴리스틱 수치·방법은 실측으로 정교화)
- 작성일: 2026-10-12
- 관련: PRODUCT-CONCEPT §8(사고 포화)·§20(그래프 폭발) · MILESTONES §M3 · 의존: D3(novelty)·D6(비용 상한) · 구현 계획: [m3-saturation-dedup](../superpowers/plans/2026-10-12-m3-saturation-dedup.md)

## 맥락

PRODUCT-CONCEPT §8은 "무한 탐색이 반복적 문장 생성으로 변하지 않도록" 사고 포화를 관찰하고(새 가설·근거·연결·confidence 변화·반복 여부), §20은 "너무 많은 유사 가설"(그래프 폭발)에 "의미 중복 감지"로 대응하라고 한다. 다중 actor(D10)로 제안량이 늘면 이 위험이 커진다(리스크 표: 그래프 슬롭 시 dedup 앞당김). MILESTONES §M3는 "단순 휴리스틱으로 시작, 임베딩은 점진, 여기서 완벽 노리지 말 것"을 명시한다.

## 결정

**읽기 전용 휴리스틱으로 중복·포화를 감지해 신호/플래그만 낸다. 삭제·자동병합·자동상태변경은 없다.**

- **near-duplicate = 정규화 토큰 Jaccard(title+claim).** 정규화 `' '.join(text.split()).casefold()`. 기본 임계 0.5(tunable). active 가설(suggested/exploring/supported/contested)끼리만 비교. branch candidate는 **부모를 제외한** active 가설과 비교(fork는 부모 파생이라 당연히 유사).
- **saturation = 최근 N(기본 3) agent run이 net-new 0.** 윈도우는 **seq 구간** — 로그에서 `operation`이 `hypothesis.*`인 `RunStarted`들을 run 경계로 삼아(framing run 제외) 최근 N번째부터 끝까지. 그 구간의 **모든 이벤트**(agent run change + `human:local` accept 포함)에서 net-new change를 센다. net-new kinds = HypothesisCreated·EvidenceCreated·EvidenceLinked·HypothesisStateChanged·ConfidenceUpdated. `saturated = (구간 내 hypothesis.* run ≥ window) and (net-new == 0)`.
- **net-new를 run 이벤트만으로 세지 않는다.** 새 가설은 accept(human:local) 이벤트에서 materialize되므로, run change만 세면 항상 0으로 오탐. 윈도우를 seq 구간으로 잡아 human 이벤트까지 포함한다.
- **삭제 이벤트 없음 → Created 수 = net-new.** replay에 삭제가 없으므로 성립.
- **노출만, 행동은 사람.** CLI `inquiry saturation`이 신호+중복을 보여주고, branch 제안 view가 near-duplicate candidate를 advisory로 표시. §8의 보류/관점변경/종료는 제안일 뿐 자동화하지 않는다.

## 근거 (provenance)

- PRODUCT-CONCEPT §8·§20의 직접 구현(외부 정본).
- MILESTONES §M3 "단순 휴리스틱으로 시작"의 준수 — 임베딩 없이 토큰 Jaccard로 출발.
- "flag-not-delete"는 §20(충돌·대안 보존) 철학과 정합 — 중복이라고 자동 제거하면 대안 경로를 잃는다.

## 결과 · 트레이드오프

- 토큰 Jaccard는 값싸고 설명 가능하나 의미 유사도엔 둔감(동의어·패러프레이즈 놓침).
- 읽기 전용이라 그래프/로그를 바꾸지 않아 안전하지만, 실제 dedup 행동(병합·archive)은 사람 몫.
- 포화 신호는 보수적(net-new 0일 때만) — 거짓 양성은 적고 거짓 음성(느린 포화)은 있을 수 있다.

## 대안 (기각)

- **임베딩 기반 의미 유사도:** 정확하나 의존성·비용·복잡도↑ → v0 범위 밖, 후속.
- **자동 병합/삭제:** 대안 경로 손실 위험(§20 위배) → flag만.
- **시간축 윈도우(weekly식):** 포화는 "탐색 반복" 개념이라 run 수축이 더 맞음 → seq/run 윈도우 채택.

## 열린 질문

- **한국어/짧은 텍스트 한계:** 공백 토큰화는 조사("가설이"/"가설은")로 유사도를 과소평가하고 `casefold()`는 한글에 무효 → 재현율 낮음. 형태소 분석/임베딩은 후속. 임계 0.5가 한국어에서 낮은 재현율일 수 있음. (M_ 후속)
- **임계·윈도우 실측 보정:** near-dup 0.5, saturation window 3은 v0 추정. 실사용 로그로 보정. (M_ 후속)
- **novelty 축(D3) 연계:** 낮은 novelty 점수를 중복 신호로 결합. (후속)
- **자동 synthesis/archive 유도**(§20) 및 **operation 제안 view 중복 플래그**. (후속)

# Inquiry

> 생각을 분기하고, 가설을 검증하고, 아이디어가 살아남거나 사라진 이유를 기록하며,
> 그 과정을 팀의 지식 자산으로 만드는 **터미널 기반 공동 탐구 환경**.
>
> A shared workspace for branching thoughts, testing hypotheses, and preserving why ideas lived or died.

**문서 상태: Concept / Pre-development** — 아직 코드는 없으며, 제품 방향과 핵심 경험을 기준 문서로 확정하는 단계입니다.

## 왜 필요한가

연구·기획·전략·창작 과정에서는 완성된 답보다 **질문과 가설이 진화하는 과정**이 중요하지만, 기존 도구는 이를 관리하지 못합니다.

- 채팅형 AI는 한 대화 안의 Q&A만, Git은 코드 변경만, 이슈 트래커는 이미 정해진 작업만 다룬다.
- 하나의 질문에서 갈라진 여러 가설, 그 가설을 왜 채택·보류·기각했는지는 시간이 지나면 사라진다.
- 여러 사람과 AI 에이전트가 지금 무엇을 탐색 중인지 한눈에 보기 어렵다.

Inquiry는 **가설(Hypothesis)** 을 중심 객체로 두고, 이 과정을 재사용 가능한 Markdown 산출물로 남깁니다.

## 핵심 개념

세 가지 객체와 세 가지 관계만으로 시작합니다.

| 사용자 표현 | 내부 표현 | 설명 |
|---|---|---|
| Question / Goal | `Inquiry` | 무엇을 알고 싶거나 이루고 싶은가 |
| Idea / Possibility | `Hypothesis` | 가능할 수 있는 답·설명·방향 |
| Check / Finding | `Evidence` | 아이디어를 더 믿거나 의심하게 만든 확인 결과 |

- `branches-from` — 이 가능성이 어떤 질문/가설에서 나왔는가
- `supports` / `challenges` — 이 Finding이 가능성을 강화/약화하는가

## 설계 원칙

- **기본 단위는 태스크가 아니라 가설이다.** 태스크는 가설을 검증하는 다음 행동일 뿐이다.
- **불확실성을 억지로 제거하지 않는다.** 모르는 부분은 조건부 가설로 분기한다.
- **에이전트의 확신을 진실처럼 표현하지 않는다.** confidence는 출처·근거 강도·범위와 함께 표시한다.
- **사람이 최종 탐구 경계를 가진다.** 비용·시간·범위·승인 경계와 종료 결정은 사람이 명시한다.
- **실패한 아이디어도 지식이다.** 기각된 가설은 삭제하지 않고 이유와 재개 조건을 보존한다.
- **그래프는 원본, 문서는 산출물이다.** canonical은 append-only 이벤트 로그, Markdown은 언제든 재생성 가능한 export.

## 경험 흐름

```text
막연한 생각 → Framing Session → 중심 질문과 초기 가설
   → 사람·에이전트의 병렬 탐구 → 근거·반례·시뮬레이션
   → 공동 Actions와 사람의 결정 → Weekly Reflection
   → Markdown 문서·연구 노트·블로그
```

핵심 인터페이스는 별도 대시보드가 아니라 Claude Code·Codex처럼 터미널에 상주하는 대화형 TUI입니다. 상단에 전체 상태, 중앙에 Possibility Map, 하단에 주간 Actions와 대화 입력을 함께 둡니다.

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/PRODUCT-CONCEPT.md`](./docs/PRODUCT-CONCEPT.md) | 제품 콘셉트 및 개발 전 기획서 (정본) |
| [`docs/REVIEW.md`](./docs/REVIEW.md) | 콘셉트 리뷰 — 결정·난점·위험 |
| [`docs/MILESTONES.md`](./docs/MILESTONES.md) | 게이트 기반 마일스톤 (M0~M5) |
| [`docs/CONVENTIONS.md`](./docs/CONVENTIONS.md) | 문서·결정·데이터·협업 규약 (사람·에이전트 공통 기준) |
| [`docs/decisions/`](./docs/decisions/) | Architecture Decision Records (ADR D1~D6) |

## 현재 상태

M0(블로킹 결정) 완료 — 6개 ADR이 모두 *Accepted*입니다.

| ADR | 결정 | 결론 |
|---|---|---|
| D1 | canonical 저장 형식 | 이벤트 로그 원본 + Markdown projection |
| D2 | 그래프 모델 | MVP는 DAG-only |
| D3 | confidence 모델 + provenance | 범위·출처 표기, 앵커 rubric |
| D4 | agent adapter 계약 | 모델 비종속 실행 인터페이스 |
| D5 | 가설 상태 머신 | 허용 전이표 + 불변식 |
| D6 | 비용 모델 | inquiry별 spend cap |

다음 단계는 M1a(Framing Session 프롬프트 검증)와 M1b(정적 TUI 레이아웃 검증)입니다. 구현 언어는 **Python** 확정.

## 라이선스

오픈소스 공개 예정 (라이선스 미확정).

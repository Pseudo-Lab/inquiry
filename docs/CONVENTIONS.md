# Conventions

> Inquiry 저장소의 문서·결정·데이터·협업 규약. 사람과 에이전트가 함께 참조하는 기준 문서다.
>
> 원칙은 하나다 — **결정과 근거를 검증 가능한 형태로 남기고, 불확실성·출처를 숨기지 않는다.**
> 이 규약 자체가 제품 철학([`PRODUCT-CONCEPT.md`](./PRODUCT-CONCEPT.md) §20, [ADR-D3](./decisions/ADR-D3-confidence-model.md))의 반영이다.

## 1. 문서 · ADR

- **결정은 ADR로 남긴다.** 파일명은 `docs/decisions/ADR-D{N}-{slug}.md` (예: `ADR-D1-storage-format.md`). `{slug}`는 kebab-case.
- **새 ADR은 [`decisions/_TEMPLATE.md`](./decisions/_TEMPLATE.md)를 복사**해 작성한다. 섹션 순서를 바꾸지 않는다:
  `맥락 → 결정 → 근거(provenance) → 결과·트레이드오프 → 대안(기각) → 열린 질문`
- **ADR 상태 생애주기:** `Proposed → Accepted → Superseded`. 대체 시 대체 ADR로 링크를 건다.
  - 이는 제품의 가설 상태([ADR-D5](./decisions/ADR-D5-state-machine.md))와 같은 형태다: Proposed=exploring, Accepted=supported, Superseded=refuted.
  - 확정 전 반드시 풀어야 하는 미결 항목은 **[미해결·확정 전 필수]**로 표시하고, 남아 있는 한 Accepted로 올리지 않는다.
- **날짜는 절대표기** `YYYY-MM-DD`. 작성일과 확정일을 분리해 적는다.
- **원문 참조는 §번호로 앵커한다.** 예: `PRODUCT-CONCEPT §16`, `REVIEW 부록 A`. 상대적 표현("위 문서")을 쓰지 않는다.
- ADR을 추가·변경하면 [`decisions/README.md`](./decisions/README.md)의 표와 상태를 함께 갱신한다.

## 2. 근거 (provenance)

이 프로젝트에서 가장 중요한 규약이다. 문서·데이터·평가 전반에 동일하게 적용된다.

- **근거는 문서 밖에 독립적으로 존재하는 것만 인정한다** — 원문 철학, 외부 자료, 실측, 사람 판단.
- **LLM·에이전트의 자체 의견을 근거로 세우지 않는다.** 순환 참조를 만들지 않기 위함이다.
- **외부 근거는 출처와 수집 시점을 남긴다.**
- **confidence는 단일 숫자로 표기하지 않는다.** 범위·출처·근거 강도를 함께 표시한다([ADR-D3](./decisions/ADR-D3-confidence-model.md)).
- 가설 채점은 `assess-hypothesis` 스킬의 앵커 rubric을 따른다.

## 3. 데이터 · ID

- **canonical은 `.inquiry/events.jsonl`** (append-only 이벤트 로그). Markdown은 projection, DB는 파생 인덱스이며 **진실이 아니다**([ADR-D1](./decisions/ADR-D1-storage-format.md)).
- **모든 상태 전이는 고정 스키마로 append한다:** `{from, to, trigger, actor, at, reason?}`([ADR-D5](./decisions/ADR-D5-state-machine.md)).
- **핵심 객체명:** `Inquiry` / `Hypothesis` / `Evidence` (PascalCase).
- **관계명:** `branches-from` / `supports` / `challenges` (kebab-case).
- **실패한 가설·기각된 대안은 삭제하지 않는다.** 이유와 재개 조건을 함께 보존한다(§4.5, §20).

## 4. Git · PR

- **기본 브랜치는 `main`.** 작업은 브랜치에서 하고 PR로 병합한다.
- **커밋 메시지에 PR 번호를 병기한다.** 예: `Add project README (#3)`.
- **ADR 관련 커밋은 ADR 코드로 시작한다.** 예: `Accept ADR-D3 (confidence rubric); ...`.
- 커밋·PR은 **무엇을 왜** 바꿨는지 한 줄로 요약하고, 관련 ADR·§번호를 링크한다.

## 5. 언어 · 스타일

- **구현 언어는 Python으로 확정**([MILESTONES](./MILESTONES.md)).
- 문서는 한국어를 기본으로 하며, 핵심 용어는 영문 병기한다(예: 가설(Hypothesis)).
- 사람이 읽고 다른 도구에서 재사용 가능한 개방형 형식(Markdown · YAML · JSONL)을 우선한다.

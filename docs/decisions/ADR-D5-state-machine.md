# ADR-D5 — 가설 상태 머신

- 상태: **Accepted** (골격 확정; 열린 질문 2건은 M3/§21.11 시점에 확정)
- 작성일: 2026-08-28
- 확정일: 2026-09-02
- 관련: PRODUCT-CONCEPT §6.5 §4.4 §4.5 · REVIEW 부록 B

## 맥락

원문 §6.5의 ASCII 다이어그램은 어느 전이가 허용되는지 애매하다. 명시적 상태 머신으로 형식화해 D1(이벤트 로그)과 정합시킨다.

## 결정

### 상태

`suggested` · `exploring` · `supported` · `contested` · `suspended` · `refuted` · `synthesized` · `human-closed`

- **터미널**(자동 전이 없음): `synthesized`, `human-closed`
- **준-터미널**(새 근거로 재개 가능): `refuted`, `suspended`

### 허용 전이 표

| From | → To | 트리거 | 주체 |
|---|---|---|---|
| `suggested` | `exploring` | 승인/탐색 시작 | human |
| `suggested` | `human-closed` | 채택 안 함 | human |
| `exploring` | `supported` | 지지 근거 우세 | agent 제안→확정 |
| `exploring` | `contested` | 유의미한 상반 근거 | agent/human |
| `exploring` | `suspended` | 판단 보류 | human |
| `exploring` | `refuted` | 반박 근거 우세 | agent 제안→사람 확정 |
| `supported` | `contested` | 새 반례 | agent/human |
| `supported` | `synthesized` | 상위 가설로 통합 | human |
| `supported` | `human-closed` | 명시 종료 | human |
| `contested` | `exploring` | 논쟁 해소 위해 재탐색 | human/agent |
| `contested` | `supported` | 반례 해소 | agent→사람 |
| `contested` | `refuted` | 반박 확정 | human |
| `contested` | `synthesized` | 통합으로 흡수 | human |
| `suspended` | `exploring` | 재개 | human |
| `refuted` | `exploring` | 새 조건·근거로 reopen | human |
| `human-closed` | `exploring` | 명시 reopen(조건 필요, §21.11) | human |

### 불변식

1. 터미널/준-터미널 → 활성 전이는 **반드시 human 주체**. 에이전트는 제안만(§4.4).
2. `synthesized` 진입 시 통합 대상(부모) 가설 ID를 이벤트에 기록(계보 보존, §6.3, D2 다부모 DAG).
3. `refuted`·`human-closed` 진입 시 **종료 이유 + 당시 근거 스냅샷 + 재개 조건** 필수 기록(§4.5).
4. 모든 전이는 D1 이벤트 로그에 `{from, to, trigger, actor, at, reason?}`로 append.

## 결과 · 트레이드오프

- 사람 확정 게이트 때문에 일부 흐름에 friction — 대신 신뢰·감사성 확보.

## 열린 질문

- `supported` ↔ `contested` flapping 방지용 confidence 히스테리시스(임계 밴드) 도입 여부.
- `human-closed` reopen 조건(§21.11)을 코드 가드로 강제할지, 정책 문서로만 둘지.

# Architecture Decision Records (ADR)

Inquiry의 M0 블로킹 결정 기록. 각 ADR은 [`../MILESTONES.md`](../MILESTONES.md) M0의 D1~D6에 대응한다.

> 상태 표기: **Proposed**(제안 — REVIEW 권장안 기반 초안) → **Accepted**(확정) → **Superseded**(대체됨)
> 진행: D1~D6 전부 *Accepted*. **M0 블로킹 결정 완료.** (D3 앵커 rubric은 `assess-hypothesis` 스킬에서 지속 calibration.)

| # | 결정 | 파일 | 상태 |
|---|---|---|---|
| D1 | canonical 저장 형식 | [ADR-D1-storage-format.md](./ADR-D1-storage-format.md) | **Accepted** |
| D2 | 그래프 모델 (DAG-only) | [ADR-D2-graph-model.md](./ADR-D2-graph-model.md) | **Accepted** |
| D3 | confidence 데이터 모델 + provenance | [ADR-D3-confidence-model.md](./ADR-D3-confidence-model.md) | **Accepted** |
| D4 | agent adapter 계약 | [ADR-D4-agent-adapter.md](./ADR-D4-agent-adapter.md) | **Accepted** |
| D5 | 가설 상태 머신 | [ADR-D5-state-machine.md](./ADR-D5-state-machine.md) | **Accepted** |
| D6 | 비용 모델 | [ADR-D6-cost-model.md](./ADR-D6-cost-model.md) | **Accepted** |

새 ADR은 [`_TEMPLATE.md`](./_TEMPLATE.md) 를 복사해 작성한다.

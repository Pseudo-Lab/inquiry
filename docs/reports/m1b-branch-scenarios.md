# 세로형 브랜치 상황별 디자인

## 선택 및 정리 완료

사용자가 이 박스형 Git-log 버전을 선택했다. 현재 작업 폴더에는 이 버전만 남겼고 A/B/C, 초기 D, 최초 지도 소스·전용 테스트·출력·옛 비교 문서는 `.omx/archive/m1b-design-history-20260916-6BtZp4/`로 이동했다. 삭제하지 않았으므로 복구할 수 있다.

필요한 셀 폭·상태·색 함수는 `presentation.py`로 분리해 옛 렌더러 의존성을 없앴다. 선택안의 18개 출력(3상황×3폭×컬러/흑백) SHA-256이 정리 전후 모두 동일하다. 관련 회귀 테스트 5개가 통과했다. 이전 문서의 17개에는 보관한 다른 디자인 테스트가 포함돼 있다.

설계 방향의 사용자 승인이며 임의 DAG나 100노드 가독성까지 검증 완료됐다는 의미는 아니다. 이후에는 이 선택안만 발전시키며, 기존 전체 노드 매트릭스를 선택안에 적용하는 작업을 남긴다.

---

GRAPH / ID / HYPOTHESIS / STATUS를 고정 폭 열로 나누고 내부 구분선을 표시한다. 주석·종료 이유는 가설 열 시작점에 맞추고 좁은 화면에서 줄바꿈한다. 제목과 Details는 전체 폭에 맞춘다. 선택 배경은 외곽선 안쪽에 한 행만 표시한다. 이미지 도구는 한글/영문의 공통 기준선을 사용하고 배경을 먼저 그려 글자 가장자리가 지워지지 않도록 한다.

2026-09-16. D 후보에서 연속·재분화·합류·종료를 보여주는 추가 정적 예시다. 실제 Git 기록이나 상태 전이 실행이 아니다.

사용자의 정렬 피드백을 반영해 그래프·가설 목록·상세를 하나의 외곽 박스 안에 배치했다. 현재 그래프 열은 5칸이며 ID 7칸·상태 16칸·가변 폭 가설 열을 사용한다.

## 1. Continue & fork

[100열 이미지](../../prototypes/m1b-layout/out/scenarios/continue-100.png)

ROOT→H-001→H-002 주계보 옆에서 H-003→H-007→H-012 지지 가지가 계속된다. H-007에서 H-011 대안 가지가 다시 갈라진다. 세 개의 열린 선을 남겨 아직 탐색 중임을 표시한다. H-011과 H-012는 형제다.

## 2. Merge & continue

[100열 이미지](../../prototypes/m1b-layout/out/scenarios/merge-100.png) · [80열](../../prototypes/m1b-layout/out/scenarios/merge-80.png)

H-002와 H-007을 두 부모로 하는 새 통합 가설 SYN-01을 만든 상황이다. 입력 가설은 Synthesized 상태로 이력에 남고, SYN-01은 Exploring 상태이며 그 뒤 H-008 탐색이 이어진다. 합류 기호 ◆는 새 통합 노드의 구조를 표시하며, 노드 자체의 상태는 오른쪽 열로 별도 표시한다. 새 노드를 곧바로 synthesized 종료 상태로 취급하지 않는다.

## 3. Refuted & closed

[100열 이미지](../../prototypes/m1b-layout/out/scenarios/endings-100.png) · [80열](../../prototypes/m1b-layout/out/scenarios/endings-80.png)

- × Refuted: 반례로 반박된 H-007 가지의 선을 끝낸다. 자동 재개는 하지 않는다.
- ⊘ Closed by user: 이번 범위 밖이라 사람이 종료한 H-005. 거짓이라는 판정과 구분한다.
- 각 가지에 Reason, Evidence 스냅샷, Reopen 조건을 남긴다. 예시는 모두 가짜 데이터다.
- 두 가지가 끝나도 H-001→H-002 주계보는 계속된다. 종료된 노드를 삭제하거나 다음 주계보의 부모로 연결하지 않는다.

이는 ADR-D2의 비순환·다부모 합류 및 ADR-D5의 반박/사람 종료 구별에 맞춘 시안이다. 실제 상태를 저장·전이하거나 승인하는 기능은 추가하지 않았다. 다시 검토할 조건을 표시하는 것과 자동으로 재개하는 것은 다르다.

## 실행과 검증

```bash
python3 prototypes/m1b-layout/branch_scenarios.py --scenario continue --color always
python3 prototypes/m1b-layout/branch_scenarios.py --scenario merge --width 80 --color always
python3 prototypes/m1b-layout/branch_scenarios.py --scenario endings --color never
python3 prototypes/m1b-layout/branch_scenarios.py --out prototypes/m1b-layout/out/scenarios
```

세 상황 × 80/100/120열의 plain/ANSI 화면을 생성했다. 현재 관련 테스트 5개 통과: 셀 폭·색 제거 시 내용 일치, 열 경계 정렬, 부모 우선 순서, 두 부모 합류·후속 가설, 종료 가지의 잘못된 연결 방지를 검사한다. 이미지는 100열 세 가지와 80열 합류·종료를 시각 검토했다.

현재 선택한 박스형 Git-log 버전만 유지한다. 이 데이터의 경로를 수동 배치한 디자인 예시이므로 임의의 DAG를 배치하는 알고리즘이나 전체 노드 수 매트릭스의 통과를 의미하지 않는다. 이미지는 셀 그리드 렌더링이며 실제 터미널 캡처가 아니다.

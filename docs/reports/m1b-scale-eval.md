# Git-log 레이아웃 규모 검증

2026-09-16. 대상: 사용자가 선택한 박스·고정 열의 세로형 Git-log 레이아웃.
기준: MILESTONES M1b, PRODUCT-CONCEPT §22-A, REVIEW C-0b. 최신 main 311e687을 현재 review-milestone-progress 브랜치에 fast-forward로 반영했다.

## 결과

**9개 조합의 자동 규모 검사 완료. M1b 전체 Exit의 최종 UX 판정은 별도다.**

| 폭 | 고유 가설 | 높이 | 페이지 수 | 첫 페이지 표시/숨김 | 보기 | 전체 회수·정렬 |
|---|---:|---:|---:|---|---|---|
| 80 | 10 | 40 | 2 | 7 / 3 | normal | 통과 |
| 80 | 30 | 40 | 5 | 7 / 23 | compact | 통과 |
| 80 | 100 | 40 | 18 | 7 / 93 | compact | 통과 |
| 120 | 10 | 40 | 2 | 7 / 3 | normal | 통과 |
| 120 | 30 | 40 | 5 | 7 / 23 | normal | 통과 |
| 120 | 100 | 40 | 18 | 7 / 93 | compact | 통과 |
| 160 | 10 | 40 | 2 | 7 / 3 | normal | 통과 |
| 160 | 30 | 40 | 5 | 7 / 23 | normal | 통과 |
| 160 | 100 | 40 | 18 | 7 / 93 | compact | 통과 |

총 75페이지를 검사했다. 각 조합의 모든 페이지에서 회수한 ID 집합이 생성한 전체 노드와 일치하며, ID 중복 생성이나 누락이 없다.

## 구현 범위

`scale.py`는 기존 연속·합류·종료 fixture를 이어 붙여 정확한 개수의 연결된 DAG를 만든다. 각 묶음의 첫 노드는 이전 묶음의 살아 있는 주계보 끝점이며 문맥으로 반복 표시한다. 실제 가설 수에 중복 계산하지 않는다. 종료된 노드를 후속 부모로 삼지 않으며, synthesized 입력에서 이어지는 것은 두 부모를 가진 통합 노드다.

숫자를 맞추기 위해 마지막 묶음을 잘라 합류를 잃는 대신, 유효한 3·5·6노드 묶음을 조합한다. 30/100노드 데이터에는 연속·재분화·두 부모 합류·반박·사람 종료가 모두 있다. 10노드는 합류와 단순 분화를 포함한다.

선택한 기존 렌더러를 재사용하며 페이지마다 전체·표시·숨김·페이지 수와 문맥 ID를 보여준다. 100개 또는 80열 30개에서는 빈 연결 행을 줄인다. 실제 노드 및 Reason/Evidence/Reopen 정보는 삭제하지 않는다. 숨김 수는 현재 페이지 밖의 고유 노드 수다.

## 증거와 재현

실측: `test_scale.py`의 네 테스트가 각 입력의 정확한 고유 개수, 부모 우선 순서, 종료 후 무단 연결 없음, 모든 페이지의 부모 참조 보존, 40행·셀 폭 일치, plain/color 내용 동등성, 전체 ID 회수를 확인한다. 기존 선택안 테스트 5개와 합쳐 9개 통과.

```bash
python3 prototypes/m1b-layout/scale.py --nodes 100 --width 80 --color always
python3 prototypes/m1b-layout/scale.py --nodes 100 --width 80 --page 3 --color always
python3 prototypes/m1b-layout/scale.py --nodes 100 --width 80 --page 18 --color always
python3 prototypes/m1b-layout/scale.py --matrix prototypes/m1b-layout/out/scale
python3 -m unittest discover -s prototypes/m1b-layout -v
```

`out/scale/manifest.json`에 9개 조합과 모든 페이지의 표시 ID·문맥·숨김 수·묶음 종류를 저장했다. 75개 plain과 75개 ANSI 스냅샷이 함께 생성된다. 이 출력은 Git에서 제외되며 재생성 가능하다.

## 화면 확인

- [80열·100개 / 합류](../../prototypes/m1b-layout/out/scale/map-80-100-p01.png)
- [80열·100개 / 종료](../../prototypes/m1b-layout/out/scale/map-80-100-p03.png)
- [80열·100개 / 마지막 페이지](../../prototypes/m1b-layout/out/scale/map-80-100-p18.png)
- [120열·30개](../../prototypes/m1b-layout/out/scale/map-120-30-p01.png)
- [160열·10개](../../prototypes/m1b-layout/out/scale/map-160-10-p01.png)

이미지는 기존 AppKit 셀 미리보기로 생성한 것이며 실제 터미널 캡처는 아니다. 자동 검사와 별개로 열·합류·종료·문맥 표시를 시각 검토했다. 에이전트의 시각 평가는 작업 메모이며 CONVENTIONS §2에 따라 사용자 가독성을 입증하는 독립 근거로 사용하지 않는다.

## 남는 절충과 다음 게이트

- 100노드는 18페이지다. 과밀을 피했지만, 페이지를 오가며 전체를 이해하는 비용은 사용자 평가가 필요하다.
- 고정된 작은 묶음과 최대 세 개의 동시 가지를 사용하는 데이터다. 임의 DAG의 광범위한 다부모 교차선이나 수십 개 동시 가지를 자동 배치하는 엔진은 아니다.
- 넓은 화면도 동일한 묶음 단위로 페이지를 나눠 여백이 많다. 폭에 따라 많은 묶음을 합쳐 배치하는 최적화는 아직 없다.
- 선택한 디자인은 위→아래=계보, 옆=분기다. 원래 위=지지/아래=반박 규칙을 그대로 충족했다고 주장하지 않는다. 사용자의 디자인 선택을 반영한 관계 이해도 확인이 남아 있다.
- 클릭·키보드 상세 탐색은 MVP 이후 일정대로 유지한다. 페이지는 CLI 옵션으로 생성하는 정적 화면이다.

이 결과로 M2를 자동 착수하거나 M1a의 잔여 UX 항목을 통과 처리하지 않는다. 다음은 페이지 요약 방식의 탐색 편의성을 확인하고 M1b의 UX 결론을 기록하는 일이다.

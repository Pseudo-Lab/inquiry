# M1b — Git-log 브랜치 프로토타입

사용자가 선택한 **박스·고정 열을 적용한 세로형 Git-log 디자인**만 유지한다.
UI는 영어, 가설 내용은 한국어이며 컬러/흑백을 모두 지원한다. Python 3.9+ 표준 라이브러리만 사용한다.

## 실행

저장소 루트에서 실행한다. API 키나 패키지 설치는 필요 없다.

```bash
# 합류 후 탐색이 이어지는 예시
python3 prototypes/m1b-layout/branch_scenarios.py --scenario merge --width 100 --color always

# 브랜치 연속·재분화
python3 prototypes/m1b-layout/branch_scenarios.py --scenario continue --width 80

# 반박·사람 종료 (흑백)
python3 prototypes/m1b-layout/branch_scenarios.py --scenario endings --color never

# 3상황 × 80/100/120열의 텍스트와 컬러 ANSI 생성
python3 prototypes/m1b-layout/branch_scenarios.py --out prototypes/m1b-layout/out/scenarios

# 회귀 검사
python3 -m unittest discover -s prototypes/m1b-layout -v
```

기본 시나리오는 continue, 기본 폭은 100이다. auto 색상은 터미널에서만 활성화되며 NO_COLOR를 존중한다.
명시적인 --color always는 NO_COLOR보다 우선한다.

## 남긴 파일

- `branch_scenarios.py`: 연속·합류·종료 예시와 CLI
- `presentation.py`: 셀 폭, 상태 표시, 컬러 표현
- `test_branch_scenarios.py`: 열 정렬·폭·부모·합류·종료 검사
- `scale.py`: 10/30/100개 연결 fixture, 문맥을 보존한 페이지 보기와 9조합 생성
- `test_scale.py`: 정확한 개수·부모 연결·전체 페이지 회수·행/열 검사
- `preview.m`: macOS 이미지 생성 보조 도구
- `out/scenarios/`: 선택 버전의 텍스트·ANSI·PNG
- `out/scale/`: 9조합의 전체 페이지와 manifest
- `out/preview`: 로컬에서 빌드한 이미지 생성기

## 이미지 보기

- [연속·분화](out/scenarios/continue-100.png)
- [합류·후속 탐색](out/scenarios/merge-100.png)
- [반박·종료](out/scenarios/endings-100.png)

PNG는 실제 터미널 캡처가 아닌 셀 그리드 렌더링이다. 실제 폰트/Unicode 설정에 따라 표시가 달라질 수 있다.
out 폴더는 Git에서 제외되며 아래 명령으로 이미지를 다시 만든다(macOS).

```bash
clang -fobjc-arc -fno-modules -framework AppKit prototypes/m1b-layout/preview.m -o prototypes/m1b-layout/out/preview
prototypes/m1b-layout/out/preview prototypes/m1b-layout/out/scenarios/continue-100.ansi prototypes/m1b-layout/out/scenarios/merge-100.ansi prototypes/m1b-layout/out/scenarios/endings-100.ansi
```

## 범위와 결정

[선택안 및 검증 기록](../../docs/reports/m1b-branch-scenarios.md)을 따른다.
수동 배치한 가짜 데이터이며 임의 DAG, 실제 상태 전이, 클릭/키보드 탐색은 구현하지 않았다.
현재 선택안의 80/120/160열 × 10/30/100노드 자동 검증은 완료했다.
연결된 작은 묶음 단위로 페이지를 나누며, 100개에서는 18페이지다. 임의 DAG의 교차선 배치와 실제 탐색 편의성까지 검증한 것은 아니다.

## 규모 검증 화면

```bash
python3 prototypes/m1b-layout/scale.py --nodes 100 --width 80 --color always
python3 prototypes/m1b-layout/scale.py --nodes 100 --width 80 --page 3 --color always
python3 prototypes/m1b-layout/scale.py --matrix prototypes/m1b-layout/out/scale
```

페이지의 첫 노드는 이전 묶음의 연결점으로 반복된다. 전체 개수에는 중복 계산하지 않는다.
페이지 밖 노드는 hidden 수에 포함되며 다른 페이지에서 모두 볼 수 있다. compact는 빈 연결 행을 줄이되 노드와 종료 기록은 보존한다.
전체 결과와 이미지: [규모 검증 보고서](../../docs/reports/m1b-scale-eval.md).

## 이전 시안 보관

A/B/C, 초기 D, 최초 지도와 전용 테스트·출력·비교 문서는 작업 폴더에서 제거하고 다음 위치로 옮겼다.

`.omx/archive/m1b-design-history-20260916-6BtZp4/`

원래 경로 구조를 보존해 복구할 수 있다. 현재 실행에 보관 폴더는 필요 없다.

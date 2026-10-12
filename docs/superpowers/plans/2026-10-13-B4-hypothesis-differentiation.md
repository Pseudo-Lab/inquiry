# B4 — 근거 기반 가설 제안 잔여분: 차별성 강화 (plan)

> 핸드오프 Track B/B4(낮음). 리서치 커넥터는 harness가 담당(피벗 해결). 남은 것은 **가설 차별성 강화** —
> difference 표시·프롬프트 개선, 중복(D11)과 연계해 **차별성 낮은 포크 후보를 사람이 보게**.

## 1. 목표 / 범위
- **목표:** 포크 후보 승인 시점에 **near-duplicate 플래그를 사람에게 노출**(이미 계산되나 미표시) + 포크 프롬프트 차별성 강화.
- **범위 밖:** 스키마/이벤트 변경(difference를 가설에 영속 — 수락 시 drop되지만 §B4는 "표시/프롬프트만"), 새 유사도 알고리즘(기존 D11 재사용).

## 2. 현황 (코드 근거)
- `saturation.near_duplicate_candidates(state, candidates, parent_id, threshold)` 존재 — 후보가 기존 활성 가설과
  유사하면 `{candidate_id, similar_hypothesis_id, score}` 플래그. (D11 token-Jaccard 재사용.)
- `BranchService._view`(service.py:54)가 `result['near_duplicates']`를 채우고, `propose`/`view`가 `_view` 반환(service.py:86) →
  **TUI·interactive 모두 proposal에 near_duplicates 보유**.
- **그러나 표시 안 함:** TUI `_branch_done`(tui.py:858)·interactive `_candidates`(interactive.py:91)는 title·claim·difference만 렌더, near_duplicates 무시.
- difference는 이미 표시됨(tui.py:865, interactive.py:96). 수락 시 `HypothesisCreated`에 difference 없음(branch/state.py) — 영속 안 됨(범위 밖).
- 포크 프롬프트 `FORK_SYSTEM`(service.py:17): "구별되는 관점 difference" 수준 — 강화 여지.

## 3. 접근

### 3.1 순수 헬퍼 (saturation.py)
- `candidate_duplicate_ids(near_duplicates)` → `{candidate_id: sorted([hyp_id, ...])}` (플래그 리스트 그룹화). 테스트 용이.

### 3.2 표시 (near_duplicate 플래그 노출)
- **TUI `_branch_done`:** 각 후보 라인에 플래그 있으면 ` ⚠유사 H-xxx` 꼬리 추가. 기존 `title — difference` 뒤에.
- **interactive `_candidates`:** 선택적 `duplicates` 맵 인자 추가(기본 None=framing 경로 불변). 포크 경로에서 전달 시 후보에 `⚠ 유사: H-xxx` 줄 추가. framing 호출(interactive.py:117)은 인자 없이 → 동작 불변.

### 3.3 프롬프트 강화 (FORK_SYSTEM)
- difference 지침 강화: 각 difference가 **서로 다른 축/메커니즘/가정**을 명시하고, 형제 후보·부모와 **겹치지 않게** 대조할 것. claim 재서술 금지(기존)·중복 회피 강조.

## 4. 수용 기준 (TDD, tests/test_differentiation.py)
1. **그룹 헬퍼:** `candidate_duplicate_ids([{candidate_id:'c1',similar_hypothesis_id:'H-002',...}, ...])` → `{'c1': ['H-002']}`, 복수 유사는 정렬 리스트.
2. **TUI 플래그 표시:** near_duplicates 있는 proposal로 `_branch_done` → Details에 `유사`·`H-xxx` 노출; 없으면 미표시.
3. **interactive 플래그 표시:** `_candidates(console, cands, duplicates={...})` → 포크 후보에 유사 마커; `duplicates=None`이면 framing 동작 불변(마커 없음).
4. **프롬프트 강화:** `FORK_SYSTEM`에 차별성 강화 키워드(축/메커니즘/겹치지) 포함.
5. **회귀:** 기존 branch/framing/tui 테스트 불변(near_duplicates 미표시였던 것 외 동작 동일).

전체 스위트 그린(기존 pre-existing 11 red 제외).

## 5. 작업 순서(TDD)
1. red: 헬퍼·표시 테스트 → 실패.
2. green: candidate_duplicate_ids + TUI/interactive 표시 + 프롬프트.
3. 회귀 확인.
4. 전체 스위트, 커밋, PR, 머지, 정리.

## 6. 위험/주의
- interactive `_candidates`는 framing·branch 공용 → `duplicates` 선택 인자로 framing 경로 완전 불변(테스트로 고정).
- difference 영속(스키마 변경)은 **하지 않음**(§B4 범위, 핸드오프 "표시/프롬프트만").
- 프롬프트 변경이 fake-adapter 결정론 테스트를 깨지 않게(프롬프트 텍스트 단언만, 출력 스키마 불변).

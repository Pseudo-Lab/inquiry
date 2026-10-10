# Inquiry

막연한 생각 하나를 **명시적인 가설**로 세우고, 그것을 분기·심화·반박·통합하며 검증해 나가는 로컬 탐구 도구다. 모든 변경은 사람이 승인한 **되감기 가능한 이벤트**로 기록되고, AI는 언제나 *제안만* 한다.

## 핵심 원칙

- **사람이 승인한다.** AI는 질문·가설·반론을 제안할 뿐, 승인(`Accept`) 전에는 가설 그래프가 바뀌지 않는다.
- **이벤트로 저장한다.** 모든 결정은 `<dir>/.inquiry/events.jsonl`에 append-only로 쌓이고, 상태는 로그를 재생(replay)해 항상 똑같이 복원된다. 숨은 상태나 자동 마이그레이션은 없다.
- **제안은 사실이 아니다.** AI의 Deepen 항목·반론·통합의 unresolved는 *검토 제안*이지 검증된 근거가 아니다. 근거(Evidence)는 사람이 직접 수집해 붙인다.
- **로컬 · BYOK.** 데이터는 로컬 파일에만 있고, OpenAI 키는 탐구 디렉터리의 `.env`에서만 읽는다. 사용료는 사용자 계정에 청구된다.

## 설치

```bash
pip install -e .          # inquiry 명령 등록
# OpenAI 연동이 필요하면 탐구 디렉터리에 .env 준비:
#   OPENAI_API_KEY=sk-...
#   INQUIRY_MODEL=gpt-5.6-terra
inquiry config check      # 공급자·모델·키 설정·권한만 확인 (키 값은 출력 안 함)
```

`inquiry <cmd>` 대신 `python -m inquiry <cmd>`도 동일하게 쓸 수 있다. 조회·승인 명령은 모델을 호출하지 않으며, 실제 생성(`Generate`/`propose`) 직전에만 비용이 발생할 수 있다.

## 빠른 시작

```bash
inquiry chat          # 대화형 탐구 (ID 복사·JSON 해석 불필요)
```

1. **Framing** — 생각을 한 줄 입력 → `Generate`로 질문을 받고 답한다 → 중심 질문·판단 기준 등 8항목 프레임과 가설 후보를 제안받아 `Accept`한다.
2. **Branch** — 승인된 가설 하나에서 서로 다른 자식 가설 후보 2~4개를 생성하고, 고른 것만 저장한다.
3. **Check** — 기존 가설을 다듬는다:
   - **Deepen** 전제·반증 조건을 보강 (주장·상태는 그대로)
   - **Challenge** 반론 1~3개를 검토 메모로 저장 (그래프는 안 바뀜)
   - **Synthesize** supported/contested 가설 2개 이상을 새 `SYN-*` 가설로 통합하고 부모를 한 번에 `synthesized`로 전환

중단해도 제출한 답변과 pending 제안은 남고, 같은 명령으로 재시작하면 모델 재호출 없이 이어진다. 거부(`Reject`)는 이유만 남기며, 새 `Generate`를 명시해야 다시 요청한다. 제안 후 대상이 바뀌면 `Stale`로 승인이 막힌다.

## 근거와 상태 전이

가설의 상태(`suggested → exploring → supported/contested → …`)는 사람이 수집한 근거로만 바뀐다. 이 명령들은 모델을 호출하지 않는다.

```bash
inquiry init --seed '반복 실수 줄이기' --question '지침을 어떻게 전달할까?'
inquiry hypothesis add --title 'handover 활용' --claim '이전 지침을 전달하면 재발을 줄인다'
inquiry start H-001
inquiry evidence add H-001 --supports --file evidence.md --type human-judgment --retrieved-at 2026-09-19T00:00:00Z
inquiry support H-001 --evidence E-001 --reason '직접 확인한 결과'
inquiry show H-001        # 현재 상태 + 과거 결정 이력 (JSON)
```

- 전이 명령: `support` / `contest` / `refute` / `suspend` / `continue` / `reopen` / `close` / `synthesize`. 각 전이는 D5 규칙으로 허용 여부를 검사하고, 당시 연결된 근거를 스냅샷으로 보존한다.
- Evidence 유형은 `external-article · measured-result · human-interview · human-judgment · dataset`만 허용한다(LLM 의견은 근거가 아니다). 원본 파일이 나중에 바뀌어도 저장된 스냅샷은 불변이다.

## 되돌아보기 (Weekly)

```bash
inquiry weekly --days 7        # 최근 7일간 '생각이 어떻게 바뀌었는지' 읽기 전용 투영
inquiry write weekly --out report.md
```

활동량이 아니라 **사고의 변화**에 초점을 둔다. 관리되는 객체가 아니라 매번 이벤트에서 다시 계산한다.

## 자동화용 단발 명령

대화형 대신 스크립트로 쓸 때. 실제 출력된 ID로 바꿔 사용한다.

```bash
inquiry branch propose H-001          # propose만 모델 호출, 나머지는 오프라인
inquiry branch accept P-... C-1 C-3
inquiry explore propose deepen H-001  # deepen | challenge | synthesize
inquiry explore accept OP-...
```

`resume`은 중단된 실행을 복구할 뿐 모델을 재호출하지 않는다. 사용량이 `unknown`이면 0으로 간주하지 않으며, 확정 토큰과 unknown 실행 수를 함께 표시한다.

## 저장 계약 (요약)

- `with Store(root) as writer`가 단일 writer 잠금(POSIX `flock`)을 얻는다. `append(event, expected_seq)`의 `expected_seq`는 기존 마지막 번호(첫 기록은 0).
- 저장 전 전체 이벤트와 재생 결과를 검증한다 — 중복 ID·잘못된 순서·다른 inquiry·알 수 없는 kind/필드는 거부하고 **기존 로그 바이트는 바뀌지 않는다**.
- 손상된 줄(잘림·잘못된 UTF-8·중복 키·NaN)은 해당 줄을 알리고 읽기/쓰기를 막는다. 자동 삭제·잘라내기는 하지 않는다.
- advisory lock은 이 도구를 쓰는 프로세스끼리의 협력 잠금이지 외부 편집을 막는 보안 경계가 아니다.

```python
from inquiry.store.store import Store
from inquiry.domain.replay import replay

with Store(root) as writer:
    writer.append(event, expected_seq=0)
restored = replay(Store(root).read_all())   # 같은 로그 → 같은 상태
```

## 검증

```bash
python3 -m unittest discover -s tests -v
```

테스트는 임시 디렉터리와 별도 프로세스를 쓰며 실제 데이터나 API를 호출하지 않는다. AI 질문·제안의 실제 유용성은 직접 사용하며 확인한다.

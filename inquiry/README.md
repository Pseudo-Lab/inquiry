# M2 — 이벤트 저장·가설·근거 코어

## 바로 사용해 보기 — 대화형 실행

현재 프로젝트 폴더의 터미널에서 다음 한 줄을 실행한다. 기존 `.env`와 `.venv`를 그대로 사용하며 API 키를 다시 입력할 필요는 없다.

```bash
.venv/bin/python -m inquiry chat
```

1. 탐구하고 싶은 생각을 한 줄로 입력한다. 저장된 초안이 있으면 그곳부터 이어간다.
2. `1. Generate`를 선택하면 AI가 질문을 만든다. **이때부터 실제 API 사용료가 발생할 수 있다.**
3. 질문에 하나씩 답하고 Enter를 누른다. 모르면 `모르겠어요`라고 답하면 된다.
4. 답변을 마치면 `Generate`를 선택해 추가 질문 또는 프레임·가설 후보를 받는다.
5. `1. Accept`는 승인, `2. Reject`는 이유를 남겨 거부, `3. Save & Exit`는 제안을 보관하고 종료한다. 거부 후에는 별도로 `Regenerate`를 선택해야 새 요청을 보낸다.
6. 승인 후에는 `1. Branch / 2. Save & Exit / 3. Check` 메뉴가 나온다. **Branch → 부모 가설 번호 → Generate branches → Accept Selected → 후보 번호(예: `1,3` 또는 `all`)** 순서로 탐구를 이어간다. 선택한 후보만 자식 가설로 저장한다.
7. 기존 가설을 구체화하려면 **Check → Deepen → 가설 번호 → Generate → Accept**를 선택한다. 기존 전제·반증 조건과 추가 제안을 구분해 보여 준다. Accept 전에는 가설을 바꾸지 않으며, 승인해도 ID·주장·부모·상태는 그대로이고 전제·반증 조건만 추가한다.
8. 반론을 검토하려면 **Check → Challenge → 가설 번호 → Generate → Accept**를 선택한다. 반론 1~3개와 각 이유·확인할 조건을 보여 주며, 전체 승인 시 하나의 검토 메모로 저장한다. **가설의 주장·상태·가지 수·근거는 바뀌지 않는다.** 반론은 모델 의견이지 독립 근거나 반박 확정이 아니다.
9. supported 또는 contested 상태인 가설을 두 개 이상 통합하려면 **Check → Synthesize → New synthesis → 부모 번호 → Generate → Accept**를 선택한다. 승인 전에는 부모나 그래프가 바뀌지 않는다. 승인하면 새 `SYN-*` suggested 가설과 모든 부모의 `synthesized` 전환을 한 기록으로 저장한다. 부모 하나라도 바뀌면 제안은 Stale이며 승인할 수 없다. 모델이 제시하는 unresolved 항목은 통합 뒤에도 남은 차이이지 검증된 사실이 아니다.
10. 저장한 메모는 **Check → Review Notes → 가설 번호**로 읽는다. 종료된 가설의 메모도 조회할 수 있으며, 이 과정에는 API 호출이나 비용이 없다. 기존 메모를 다음 생성 요청에 자동으로 보내지도 않는다.

Deepen 제안 화면에서 `Save & Exit`를 선택한 뒤 같은 명령으로 재시작하고 Check → Deepen → 같은 가설을 고르면 API 재호출 없이 저장된 제안을 보여 준다. `Reject`는 이유와 거부 이력만 저장하며 자동으로 다시 생성하지 않는다. 제안 후 가설이 바뀌면 `Stale`로 표시하고 승인을 막는다. 거부 후 새 Generate를 명시 선택해야 다시 요청한다. `suggested`, `exploring`, `supported`, `contested` 상태에서만 새 Deepen을 생성한다.

승인된 추가 항목은 `.venv/bin/python -m inquiry show H-001`처럼 실제 가설 ID로 조회할 수도 있다. 이 조회에는 API 키나 모델 호출이 필요 없다. 단발 명령은 `explore propose deepen H-001`, `explore show OP-ID`, `explore accept OP-ID`, `explore reject OP-ID --reason '이유'`, `explore resume`이다. OP-ID는 생성 결과의 실제 제안 ID로 바꾼다. `propose`의 새 생성에만 API 비용이 발생할 수 있으며 `resume`은 미종결 실행을 복구할 뿐 모델을 재호출하지 않는다.

Challenge와 Synthesize도 같은 승인·거부·재개 규칙을 쓴다. `Save & Exit` 후 같은 대상을 다시 열면 저장된 제안을 API 없이 보여 준다. 단발 생성은 `explore propose challenge H-001`, `explore propose synthesize H-001 H-002`이며 메모 조회는 `explore notes H-001`이다. 반론 일부 선택·메모 편집·삭제는 아직 지원하지 않는다. Synthesize는 supported/contested 부모 두 개 이상만 생성할 수 있고, 승인 때 부모 전부를 동시에 전환한다. 메모 승인만으로 기존 Deepen 제안이 무효화되지는 않지만, Deepen 승인으로 가설이 바뀌면 이전 Challenge 제안은 `Stale`이 되어 승인할 수 없다.

질문·메뉴에서 `/exit` 또는 Ctrl-C로 종료할 수 있다. 제출한 답변은 남고, **같은 실행 명령으로 다시 시작하면 이어서 진행한다.** 승인된 탐구가 있으면 모델 호출 없이 저장된 요약과 Branch 메뉴를 보여 준다. 기존 탐구를 지우거나 자동으로 새 탐구로 바꾸지는 않는다.

`Paused`에 `cancelled / timeout`이 표시되면 앱의 실행 제한을 넘긴 것이다. 제출한 답변은 유지된다. `Resume`은 모델 호출 없이 초안을 복구하고, 이후 직접 `Generate`를 선택해야 새 요청을 보낸다. `Usage: unknown`은 사용량이 0이라는 뜻이 아니므로 반복 생성에 주의한다. 로컬 저장 병목을 줄였지만 실제 모델·네트워크 응답 시간까지 보장하지는 않는다.

OpenAI 중간 출력은 첫 조각 이후 1,024자 또는 수신 시간 1초 단위로 묶어 기록한다(새 출력이 도착할 때 판단하며 저장 처리 시간은 제외). 중간 기록은 일부가 생략될 수 있는 관찰용 정보다. 완료 이벤트 앞에서 남은 조각을 별도로 저장하지 않으며, 최종 제안과 확인된 사용량은 완료 응답에서 가져온다. 저장 원본 검증과 실행 제한은 그대로 유지한다.

실제 터미널에서는 Python의 `readline`을 사용해 한글을 글자 단위로 편집한다. 이전 실행에서 한글 Backspace가 제대로 동작하지 않았다면 `/exit` 또는 Ctrl-C로 나간 뒤 `chat`을 다시 실행한다. 별도 패키지 설치나 iTerm 설정 변경은 이번 수정에 필요하지 않다. Python 빌드에 `readline`이 없으면 터미널 입력 전에 안내 오류를 표시하며, 파이프 입력과 저장된 결과 조회는 그대로 사용할 수 있다.

**현재는 텍스트 화면에서 Framing·Branch·Deepen·Challenge·Synthesize를 제공한다. Git-log TUI는 사용성 검증(Gate B) 후 연결할 예정이며 이번 화면에 포함되지 않는다.** Deepen 항목, Challenge 반론, Synthesize의 unresolved 항목은 검토 제안이지 검증된 사실이 아니다. 실제 모델 질문과 제안의 유용성은 직접 사용하며 확인한다. 자동 테스트가 이 사용성 판단을 대신하지 않는다.

처음 설치하거나 `.venv`가 없다면 아래 준비 명령을 한 번 실행한다. 기존 `.env`는 덮어쓰지 않는다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

다른 탐구 디렉터리를 쓰려면 `.venv/bin/python -m inquiry --dir /path/to/inquiry chat`으로 실행한다. 그 디렉터리의 `.env`가 사용된다. 선택 제한은 `chat --max-output-tokens 4000 --timeout 60`이며 금액 상한이 아닌 **요청별** 출력 토큰·시간 설정이다.

이 아래는 설정·저장 코어 및 단발 명령을 위한 상세 참고다. 대화형 사용에 ID 복사나 JSON 해석은 필요하지 않다.

Python 3.9+를 사용한다. 저장 코어는 표준 라이브러리로 동작하고 현재 쓰기 잠금은 macOS/Linux의 POSIX `flock`을 사용한다. OpenAI 연결에 필요한 선택 의존성 범위는 코드 루트의 `requirements.txt`에 고정한다. 전용 가상환경에 설치하며 시스템 Python 패키지를 변경할 필요는 없다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

CLI는 OpenAI SDK `2.48.0` 이상 `3.0.0` 미만을 확인한다. 의존성이 없거나 범위와 맞지 않으면 실제 Run을 시작하기 전에 고정된 설치 안내로 종료한다.

## 프로젝트 전용 OpenAI 설정

탐구 명령의 `--dir`로 지정할 디렉터리 바로 아래에 `.env`를 둔다. 이 위치는 코드 저장소 루트일 필요가 없다. 새 파일을 만들 때만 `.env.example`을 복사하며, 기존 `.env`를 예제로 덮어쓰지 않는다. 기존 파일에 키가 이미 있다면 `INQUIRY_MODEL`만 직접 추가한다. 예시 모델은 `gpt-5.6-terra`이며 자동으로 대체되는 기본 모델은 없다. `.env`는 이 탐구 디렉터리에서만 읽고 상위 디렉터리나 셸 환경변수로 대체하지 않는다.

```dotenv
OPENAI_API_KEY=sk-example-not-a-real-key
INQUIRY_MODEL=gpt-5.6-terra
```

평문 키 파일이므로 소유자만 읽고 쓸 수 있게 만들고 Git에서 제외해야 한다. 도구가 권한이나 ignore 설정을 자동 변경하지는 않는다.

```bash
chmod 600 /path/to/inquiry/.env
# /path/to/inquiry가 Git 작업 트리 안에 있을 때만:
printf '\n.env\n' >> /path/to/inquiry/.gitignore
.venv/bin/python -m inquiry --dir /path/to/inquiry config check
```

`config check`는 실제 생성 전에 선택적으로 실행할 수 있다. 공급자, 모델, 키 설정 여부, 파일 권한과 Git 보호 상태만 표시하며 키 값·일부·길이·해시는 표시하지 않는다. 키가 노출되었거나 더 이상 필요하지 않다면 `.env`에서 제거하고 OpenAI 대시보드에서 즉시 폐기한 뒤 새 키로 교체한다.

## 실행 가능한 최소 예시

저장소 루트에서 Python을 실행한다. `TemporaryDirectory` 대신 실제 탐구 디렉터리를 전달하면 기록이 유지된다.

```python
from tempfile import TemporaryDirectory
from inquiry.store import Store
from inquiry.replay import replay

event = {
    "schema_version": 1,
    "event_id": "event-1",
    "seq": 1,
    "inquiry_id": "I-001",
    "actor": "human:local",
    "at": "2026-09-17T00:00:00Z",
    "type": "changes-committed",
    "changes": [{
        "kind": "InquiryCreated",
        "seed": "같은 실수를 반복하지 않으려면?",
        "frame": {"question": "이전 세션의 지침을 어떻게 전달할까?"},
    }],
}

with TemporaryDirectory() as root:
    with Store(root) as writer:
        writer.append(event, expected_seq=0)
    restored = replay(Store(root).read_all())
    print(restored.inquiry.seed)
    print(restored.last_seq)  # 1
```

## 계약

- 원본은 `<root>/.inquiry/events.jsonl`이다. 한 변경 묶음이 UTF-8 JSON 한 줄이며 끝에 newline이 있다.
- `Store(root)` 생성과 `read_all()`은 원본이 없으면 빈 이력을 반환하며 파일을 만들지 않는다.
- `with Store(root)`는 단일 writer 권한을 얻는다. `append(event, expected_seq)`의 expected_seq는 **기존 마지막 번호**다. 첫 기록에서는 0을 사용한다.
- Store는 생성 시 루트를 절대 경로로 고정한다. writer 컨텍스트는 소유 프로세스·스레드에서만 사용하며 다른 스레드가 읽기/추가/close를 할 수 없다. fork된 자식은 부모의 writer 권한을 재사용할 수 없다.
- 같은 writer 안의 `read_all()`은 가능하다. 다른 writer/reader가 잠금과 충돌하면 `StoreBusyError`를 반환한다.
- 저장 전 전체 이벤트와 재생 결과를 검증한다. 중복 ID, 잘못된 순서, 다른 inquiry, 알 수 없는 버전·kind·필드는 거부한다.
- 쓰기에는 파일 flush/fsync와 로그 디렉터리 fsync를 수행하고 새 디렉터리의 부모 항목도 동기화한다. 이 호출의 성공을 실제 전원 장애 시험과 동일시하지는 않는다.
- 읽기와 `replay()`는 모델을 호출하거나 복구 이벤트를 자동 추가하지 않는다. 같은 로그는 같은 상태로 재생된다.

## 현재 지원하는 변경

| kind | 필수 필드 | 재생 결과 |
|---|---|---|
| `FramingStarted` | `session_id`, `seed` | 예약된 inquiry ID 아래 시작된 draft 세션 |
| `FramingControlRecorded` / `QuestionsIssued` | session/run ID, 판단 및 응답 qid / batch ID와 질문 | 성공 Run과 함께 저장된 다음 질문 또는 완료 판단 |
| `AnswerRecorded` | session_id, qid, answer | 덮어쓰지 않는 제출 답변 |
| `FrameProposed` | session/proposal/run ID, frame, qa | 검증된 프레임과 원본 Q&A |
| `FramingCancelled` / `FramingResumed` / `FrameRejected` | session ID, reason, 거부 시 proposal ID | 초안을 보존하는 진행/제안 상태 |
| `FrameAccepted` | session/proposal/inquiry ID, hypothesis_ids | inquiry와 가설 생성에 결합된 사람 승인 |
| `InquiryCreated` | `seed`, `frame` JSON 객체 | inquiry 최초 생성 |
| `HypothesisCreated` | ID, title, claim, parent_ids, assumptions, falsified_if | suggested 가설과 DAG 계보 |
| `EvidenceCreated` | ID, type, content, uri, retrieved_at, actor | 파일 내용과 출처의 스냅샷 |
| `EvidenceLinked` | evidence_id, hypothesis_id, relation | supports/challenges 연결 |
| `HypothesisStateChanged` | from/to, trigger, actor, at, reason 및 근거/종료/합류 메타데이터 | D5 규칙으로 상태 변경 및 결정 이력 보존 |
| `RunStarted` / `RunDispatched` | run_id, 모델·대상·제한 / run_id | 실행 예약과 호출 진입 기록 |
| `RunProgress` / `RunHeartbeat` | run_id, 실제 출력/신호, provider_request_id | 실행 중 관찰 기록 |
| `RunSucceeded` / `RunFailed` / `RunCancelled` | 최종 proposal 또는 reason, usage 및 provider 정보 | 실행 결과 저장 |
| `RunUsageReported` | run_id, known usage, provider_request_id | 미확인 사용량 보완, 중복 집계 방지 |

각 변경에는 `kind`도 필수다. 같은 session ID나 inquiry를 다시 생성할 수 없다. 다른 kind는 조용히 무시하지 않고 오류로 처리한다.

수동 `init`의 frame은 JSON 객체다. Framing 경로는 별도로 8항목과 후보 2~4개를 검증하며, 사람의 승인 전에는 inquiry나 가설을 만들지 않는다. M2-4A의 OpenAI 연결은 아래 CLI 경로로 제공하며, 실제 계정 접근·모델 품질 검증은 오프라인 테스트와 별개다.

## Framing draft 저장과 승인

`inquiry.framing.FramingService`는 질문 → 제출 답변 → 제안 → 승인 흐름을 저장한다. CLI는 실제 생성이 필요한 `framing next`에서만 프로젝트 설정과 OpenAI 어댑터를 지연 로드한다. 저장된 질문·pending 제안·승인된 세션을 조회하거나 `show`/`resume`/`accept`를 실행할 때는 키나 SDK를 읽지 않는다.

- `start(seed)`: 첫 호출 전에 seed와 세션 ID를 저장한다.
- `advance(session_id, adapter)`: 처음에는 3문항, 이후에는 누적 5문항 안에서 추가 질문 또는 프레임을 생성한다. 미응답 질문이나 pending 제안이 있으면 다시 호출하지 않고 저장된 내용을 반환한다.
- `answer(session_id, qid, text)`: 제출한 답변을 즉시 저장한다. 같은 답변은 중복 기록하지 않으며 다른 답변으로 덮어쓰지 않는다. 모르는 내용도 명시적으로 답할 수 있다.
- `view(session_id)`: 읽기 전용 조회. `resume(session_id)`는 중단된 Run을 명시적으로 복구하고 취소한 세션을 재개하지만 모델을 호출하지 않는다.
- `reject(session_id, proposal_id, reason)`: 거부한 제안을 이력으로 남긴다. 다시 만들려면 `advance(..., regenerate=True)`를 명시한다.
- `accept(session_id, proposal_id)`: 저장된 제안의 승인·inquiry 생성·suggested 가설 생성을 한 이벤트에 기록한다. 같은 제안을 다시 승인하면 기존 ID만 반환한다.
- `cancel(session_id)`: 초안을 보존하고 진행을 멈춘다. 승인된 가설을 삭제하는 명령이 아니다.

프레임은 중심 질문, 목적, 사용 맥락, 현재 생각, 판단 기준, 포함/제외 범위, 열린 질문, 가설 후보의 8항목이다. 후보마다 ID·제목·주장·차별 축이 필요하며 실제 제출 Q&A를 제안에 함께 보존한다. 정확히 같은 후보 제목/주장은 거부하지만 의미상 차이를 자동 판정하는 것은 아니다.

질문/제안은 `RunSucceeded`와 같은 줄에 저장한 뒤 반환한다. 승인 전 취소·거부·잘못된 모델 결과는 그래프를 변경하지 않는다. 출력 전에 프로세스가 종료돼도 저장된 질문 ID·답변·제안·승인 결과를 재사용한다. 제출하지 않은 입력 문자는 복구 대상이 아니다.

`Runner.execute`의 `preflight`/`success_changes`는 애플리케이션 소유 검증 함수다. writer 잠금 아래에서 오래된 세션 상태를 확인하고, 성공과 draft 변경을 원자적으로 저장한다. 모델이 이벤트나 승인 명령을 직접 제공하는 인터페이스가 아니다. 프레임 검증 실패는 `invalid-proposal`로 기록하며 실제 보고된 사용량을 보존한다.

`cancellation_changes`는 Run 취소와 세션 취소를 같은 이벤트에 결합한다. 취소 저장 직후 종료되더라도 재시작 후 세션은 cancelled이며, 명시적 `resume` 전에는 다시 실행하지 않는다.

기존 저장 코어 테스트에서 사용하던 `FramingStarted → InquiryCreated` 직접 생성은 이제 거부한다. draft가 있는 로그는 유효한 승인 묶음을 거쳐야 하며, 이 경계를 우회하는 초기 합성 로그의 자동 마이그레이션은 제공하지 않는다.

CLI 예시(출력된 실제 ID로 `F-...`, `Q-...`, `P-...`를 바꾼다):

```bash
python3 -m inquiry --dir demo-framing framing start --seed '다른 세션에서 같은 실수를 반복하지 않으려면?'
python3 -m inquiry --dir demo-framing framing next F-...
python3 -m inquiry --dir demo-framing framing answer F-... Q-... 'handover를 만들어 사용했다'
python3 -m inquiry --dir demo-framing framing next F-...
python3 -m inquiry --dir demo-framing framing accept F-... P-...
```

각 명령의 JSON 출력에 있는 실제 `F-...`, `Q-...`, `P-...` ID를 다음 명령에 사용한다. `framing next`에는 `--model <id>`, `--max-output-tokens <n>`, `--timeout <seconds>`를 선택적으로 지정할 수 있다. 모델 override가 없으면 `.env`의 `INQUIRY_MODEL`을 사용한다. 토큰 상한 override가 없으면 control 4,000, proposal 16,000이며 timeout은 호출마다 60초다. 완료 control은 proposal 생성을 위한 두 번째 호출을 자동으로 시작할 수 있다.

실제 호출 직전 stderr 안내에는 공급자·모델·호출별 상한과 비용 가능성이 표시된다. OpenAI에는 프레이밍 seed와 지금까지 제출한 Q&A가 전송되므로 민감한 정보를 넣지 않는다. API 사용료는 사용자 계정에 청구될 수 있으며 이 도구는 금액을 추정하지 않는다. `.env`를 저장하는 것만으로는 호출하지 않으며, 저장된 결과를 반환하는 `framing next`도 호출하지 않는다. 네트워크 없는 fake 흐름은 `python3 -m unittest tests.test_openai_cli tests.test_framing_flow tests.test_framing_process -v`로 실행할 수 있다.

공급자 요청은 고정된 공식 endpoint `https://api.openai.com/v1`로만 보내며 redirect를 따르지 않는다. 환경변수의 HTTP(S) proxy 설정도 읽지 않으므로 proxy가 필요한 네트워크는 현재 지원하지 않는다.

## 가설을 이어가는 Branch

같은 `chat`에서 승인된 가설 하나를 선택해 서로 다른 후보 2~4개를 생성한다. 생성 자체는 부모나 그래프를 바꾸지 않는다. 후보를 읽고 Accept Selected로 고른 것만 부모를 참조하는 새 `suggested` 가설이 된다. 부모 상태나 Evidence는 자동으로 바뀌지 않는다.

- `Save & Exit` 후 같은 부모를 선택하면 pending 제안을 그대로 복원하며 다시 과금 호출하지 않는다.
- 거부한 제안은 이유와 함께 남는다. 이후 Branch/Generate를 명시적으로 선택해야 새 제안을 만든다.
- 제안 뒤 부모 상태가 바뀌면 Stale로 표시하고 승인을 차단한다. pending 제안은 읽거나 거부할 수 있다.
- 한 번 승인한 제안에는 후보를 뒤늦게 추가할 수 없다. 다른 아이디어가 필요하면 새 Branch를 실행한다. 선택하지 않은 후보도 제안 기록에서 사라지지 않는다.
- 미종결 실행은 Resume으로 명시 복구한다. 공급자 처리 여부와 사용량이 unknown이면 0으로 간주하지 않는다. 화면에는 확인된 누적 토큰과 unknown 실행 수를 함께 표시한다.
- API로 보내는 것은 탐구 프레임과 선택한 부모의 ID·제목·주장·부모 ID·상태·전제·검증 조건이다. 전체 결정 이력이나 근거 스냅샷, 임의 프로젝트 파일은 보내지 않는다.

자동화용 단발 명령도 제공한다. 실제 출력 ID로 예시를 바꿔 사용한다.

```bash
.venv/bin/python -m inquiry --dir . branch propose H-001
.venv/bin/python -m inquiry --dir . branch show P-...
.venv/bin/python -m inquiry --dir . branch accept P-... C-1 C-3
.venv/bin/python -m inquiry --dir . branch reject P-... --reason '다른 관점이 필요함'
.venv/bin/python -m inquiry --dir . branch resume
```

`propose`만 필요할 때 모델을 호출하며 나머지는 오프라인이다. 같은 제안/같은 선택의 중복 승인은 기존 ID를 반환한다. 실제 SDK 연결도 fake HTTP transport로 검증했으며, 사용자 계정의 모델 품질이나 실제 과금을 확인한 것은 아니다.

## 실행 계약과 fake adapter

비어 있지 않은 `OPENAI_CUSTOM_HEADERS` 환경변수는 지원하지 않는다. SDK가 이 값으로 프로젝트의 인증·조직·Host 설정을 덮어쓸 수 있으므로 새 Run 전에 차단한다. 해당 환경 설정을 제거한 실행 환경에서 다시 시도한다. 도구가 전역 환경을 자동 변경하거나 값을 출력하지는 않으며, 저장된 질문·제안 조회는 계속 가능하다.

`Adapter.run(RunRequest)`는 progress/heartbeat/usage/succeeded/failed/cancelled 신호를 전달하는 iterator다. SDK는 이 계약 밖의 구체 어댑터에만 둔다. 아래 코드는 네트워크 없이 실행된다.

```python
from tempfile import TemporaryDirectory
from inquiry.adapter import RunRequest, RunSignal
from inquiry.runs import Runner

class DemoAdapter:
    def run(self, request):
        yield RunSignal('progress', text='질문 제안을 만드는 중')
        yield RunSignal('succeeded', proposal={'questions': ['무엇을 확인하고 싶나요?']})

with TemporaryDirectory() as root:
    runner = Runner(root)
    request = RunRequest('I-demo', 'R-demo', 'framing.questions', 'fake', {'seed': '생각'})
    result = runner.execute(request, DemoAdapter())
    print(result.status)              # succeeded
    print(result.usage['input_tokens'])  # None: 사용량을 보고하지 않은 가짜 실행
    print(runner.totals()['unknown_runs'])  # 1
```

- 시작 기록을 저장한 뒤 어댑터를 호출한다. 성공 상태·proposal·최종 usage는 같은 이벤트에 저장하고 그 뒤 반환한다. proposal은 아직 승인되지 않은 데이터이며 가설 그래프를 자동 변경하지 않는다.
- 동일 run_id는 다시 실행하지 않는다. 저장된 결과는 `runner.get(run_id)`로 읽는다. 사용자가 새 실행을 요청할 때 새 ID를 사용한다.
- `runner.recover()`는 미종결 Run을 `process-interrupted`로 한 번만 실패 처리한다. 어댑터를 호출하지 않는다. 단순 조회와 replay는 복구 이벤트를 쓰지 않는다.
- `usage.status`는 known/unknown/not-started다. unknown은 토큰 null이고, 호출 전 취소한 not-started만 0이다. provider가 명시한 0은 known이다.
- `runner.totals()`의 input_tokens/output_tokens는 **확인된 부분 합계**다. unknown_runs가 0보다 크면 총사용량이 확정된 것이 아니므로 반드시 함께 표시해야 한다. 금액 합계는 이 메서드가 계산하지 않는다.
- `runner.report_usage(run_id, usage, provider_request_id=...)`는 늦게 확인된 최종 사용량을 반영한다. 같은 보고는 파일 변경 없이 반환하고, 다른 값이나 다른 provider ID는 거부한다. 이미 known인 usage의 비용/가격 출처만 바꿔 덮어쓰는 것도 허용하지 않는다.
- RunStarted에는 요청 context나 인증 정보를 저장하지 않는다. 어댑터 예외는 raw message 대신 예외 클래스만 기록한다. partial output/proposal은 의도된 실행 결과로 저장될 수 있다.
- `cancelled=event.is_set` 콜백으로 협조적 취소를 요청할 수 있다. Runner는 신호 사이에서 취소·timeout을 검사하며, **블로킹 I/O의 시간 제한은 어댑터가 지켜야 한다**. 임의의 Python 실행을 강제 종료하는 기능이 아니다.
- 일반 iterator 정리 오류는 `runner.cleanup_errors[run_id]`에 예외 클래스명만 남긴다. 이 진단은 프로세스 로컬이며 이미 저장된 결과나 원래 저장 예외를 바꾸지 않는다. 종료용 BaseException은 그대로 전파한다.

확정 usage에는 input_tokens/output_tokens와 est_cost/price_ref 필드를 모두 전달한다. 가격 출처가 없으면 est_cost는 null이다. 알려진 사용량 뒤에 실행이 중단돼도 그 값을 잃거나 0으로 바꾸지 않는다.

## 사람이 실행하는 가설·근거 명령

```bash
python3 -m inquiry --dir demo-inquiry init --seed '반복 실수 줄이기' --question '지침을 어떻게 전달할까?'
python3 -m inquiry --dir demo-inquiry hypothesis add --title 'handover 활용' --claim '이전 지침을 전달하면 재발을 줄일 수 있다'
python3 -m inquiry --dir demo-inquiry start H-001

# evidence.md는 직접 수집한 관찰/판단을 적은 UTF-8 파일
python3 -m inquiry --dir demo-inquiry evidence add H-001 --supports --file evidence.md --type human-judgment --retrieved-at 2026-09-19T00:00:00Z
python3 -m inquiry --dir demo-inquiry support H-001 --evidence E-001 --reason '직접 확인한 결과'
python3 -m inquiry --dir demo-inquiry show H-001
```

이 명령은 모델을 호출하지 않는다. `init`/`hypothesis add`는 사람이 작성한 입력을 코어에 넣는 방법이며, Framing 승인 UI를 구현한 것은 아니다. ID는 저장된 객체에서 정하고 재시작 후에도 기존 ID를 재사용하지 않는다. 출력은 JSON이며 `show`에는 현재 상태와 과거 결정 이력이 포함된다.

- `hypothesis add --parent H-001`: 계보 연결. 중복 부모·자기 참조·없는 부모·순환은 거부한다. 비활성 부모에서 새 가지를 만들려면 먼저 재개해야 한다.
- `evidence link E-001 H-002 --challenges`: 같은 근거를 다른 가설에 연결. 근거 생성만으로 가설 상태는 바뀌지 않는다.
- `contest`/`refute`: 현재 가설에 challenges로 연결된 근거가 필요하다. `support`에는 supports 근거가 필요하다.
- `refute H-001 --evidence E-001 --reason '반례' --reopen-if '조건 변경'`: 현재 연결된 근거 전체를 스냅샷으로 보존한다.
- `close H-001 --reason '범위 밖' --reopen-if '범위 변경'`: D5에서 허용된 suggested/supported 상태에서만 직접 종료한다. 탐색 중이거나 논쟁 중인 가설을 임의로 직접 종료하지 않는다.
- `suspend H-001 --reason '판단 보류'`: exploring→suspended. `continue H-001 --reason '다시 검토'`는 contested→exploring이다.
- `reopen H-001 --reason '조건 충족' --condition-evidence E-001`: 사람이 해당 inquiry의 근거를 참조해 재개한다. 조건을 자동 평가하지 않는다. 이전 종료 이유와 스냅샷은 결정 이력에 남는다.
- `synthesize H-001 H-002 --title '통합안' --claim '통합 주장' --reason '두 접근 결합'`: supported/contested 부모 두 개 이상으로 새 suggested 가설을 만들고, 모든 부모를 synthesized로 바꾸는 변경을 한 줄에 기록한다. 일부 부모만 바뀌는 합류는 거부한다. AI 제안은 `explore propose synthesize H-001 H-002`에서 생성하고, `explore accept OP-...`로 승인한다.

CLI는 사람이 로컬에서 수행한 결정으로 기록한다. 주체를 바꾸는 `--by` 옵션은 없다. 저장된 이벤트는 전이 주체·시각과 envelope의 일치를 검사한다. 파일을 직접 수정할 수 있는 사용자를 상대로 인증을 제공하는 시스템은 아니다.

Evidence 유형은 external-article, measured-result, human-interview, human-judgment, dataset만 허용한다. external-article/dataset에는 URI가 필수다. 모든 유형에 내용·수집 시점·주체가 필요하다. 원본 파일이 나중에 바뀌어도 저장된 스냅샷은 바뀌지 않는다. LLM 의견을 근거로 저장하는 타입은 없으며, 사용자가 잘못 붙인 출처나 자료의 진위까지 자동 검증하지는 않는다.

## 실패 시 동작

- 스키마·중복·순서·재생 검증 실패: 기존 로그 바이트가 바뀌지 않는다.
- 잘린 마지막 줄, 잘못된 UTF-8, 중간 손상, JSON 중복 키·NaN: 해당 줄을 알려주고 읽기/추가 쓰기를 차단한다. 자동 삭제나 잘라내기는 하지 않는다.
- 디스크 쓰기·동기화 실패: 전체 또는 일부 기록이 남을 수 있다. 결과를 알 수 없다는 오류를 반환하며 롤백이나 자동 재시도를 약속하지 않는다. 재시도 전 실제 로그를 확인해야 한다.
- advisory lock은 이 Store를 사용하는 프로세스끼리 협력하는 잠금이다. 외부 편집기나 다른 프로그램이 직접 로그를 바꾸는 것을 막는 보안 경계가 아니다.

## 검증

```bash
python3 -m unittest discover -s tests -v
```

테스트는 임시 디렉터리와 별도 프로세스를 사용한다. 실제 프로젝트 데이터나 API를 사용하지 않는다. 프로세스 강제 종료는 검사하지만 실제 전원 장애나 네트워크 파일시스템의 내구성을 검증한 것은 아니다.

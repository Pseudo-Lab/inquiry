# M2-4A OpenAI BYOK Framing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task. 현재 문서는 계획이며 구현 완료 표기가 아니다.

**Goal:** 사용자가 프로젝트 전용 키로 CLI에서 Framing 질문·프레임을 생성하고 저장·승인하는 전체 경로를 사용한다.

**Architecture:** 로컬 설정 → 지연 생성 OpenAI adapter → 기존 Runner → FramingService의 검증·원자적 저장 경계를 유지한다. 공급자 결과는 제안이며 승인 없이 그래프를 변경하지 않는다. 키는 요청 context나 이벤트에 넣지 않는다.

**Tech Stack:** Python 3.9+, 기존 표준 라이브러리 코어, 기존 프로토타입 의존성 `openai>=2.48.0,<3`, `python-dotenv>=1.0,<2`. 새로운 종류의 의존성은 추가하지 않는다.

## Global Constraints

- 정본: [M2 전체 계획 §6](2026-09-17-m2-implementation.md), [ADR-D8](../../decisions/ADR-D8-local-byok-distribution.md), [ADR-D4](../../decisions/ADR-D4-agent-adapter.md).
- 이번 범위는 M2-4A뿐이다. 가설 5연산(M2-4B), TUI, 설치 패키지 배포, 로그인 서버, 로컬 모델, Codex/Claude 연동은 제외한다.
- 기존 linked worktree와 미커밋 변경을 보존한다. 사용자 실키를 읽거나 출력하지 않는다. 테스트에는 합성 키만 사용한다. 커밋·푸시는 별도 요청으로만 한다.
- 기본 테스트는 네트워크 없이 실행한다. 실제 smoke는 사용자에게 호출 상한과 전송할 합성 입력을 제시하고 명시적으로 실행 요청받은 뒤 별도 수행한다. 계획 승인은 실제 과금 호출 승인이 아니다.
- 사용성 Gate B와 TUI 차단 조건은 유지한다. 자동 테스트나 합성 대화를 실제 사용자 UX 검증으로 바꾸지 않는다.

## 설계 선택과 대안

1. **선택: 프로젝트 `.env`를 명시적으로 읽고 사용자에게 직접 편집하게 한다.** 이미 합의된 프로젝트 범위 키 방식과 호환되고 OS별 키 저장소·키 덮어쓰기 명령이 필요 없다. 평문 파일이므로 권한·Git 제외를 검사하고 암호화 저장이라고 표현하지 않는다.
2. OS 키 저장소: 평문 파일 노출을 줄이지만 플랫폼별 구현/의존성이 필요해 후속 개선으로 둔다.
3. shell export만 지원: 프로젝트 전용 사용 요구에 맞지 않아 기본 경로에서 제외한다.

모델은 `--model` 또는 프로젝트 설정으로 명시한다. 과거 프로토타입 기본값을 새 CLI의 숨은 기본값으로 가져오지 않으며 계정 접근 가능성도 추측하지 않는다. 요청한 모델 실패 시 다른 모델로 자동 대체하지 않는다.

### 키·설정 계약

- `--dir`의 절대 경로 바로 아래 `.env`만 읽는다. 상위 폴더 탐색, cwd/전역 환경변수 fallback, `load_dotenv()`로 프로세스 환경 변경을 하지 않는다.
- `.env` 필드: `OPENAI_API_KEY`, `INQUIRY_MODEL`. API 키 CLI 인자는 만들지 않는다. 키를 표시·복사·자동 수정하는 명령도 만들지 않는다.
- `dotenv_values(path, interpolate=False)`로 문자열 치환 없이 읽는다. 중복 설정 키·빈 키/모델은 안전한 오류로 거부한다. 파서 원문 경고가 stderr로 새지 않게 포착하고 일반 오류로 대체한다.
- `.env`는 일반 파일, 현재 UID 소유, group/other 접근 비트가 없는 파일만 허용한다. symlink와 비정규 파일은 거부한다. descriptor 기반 O_NOFOLLOW/fstat로 읽기 전후 경로 바꿔치기에 의한 우회를 막는다. 잘못된 권한은 파일을 자동 변경하지 않고 사용자 수정 방법을 안내한다.
- Git 저장소면 `.env`가 이미 tracked인지, ignore되는지 검사한다. tracked 또는 unignored면 온라인 실행을 거부하고 조치를 안내한다. 저장소 밖은 적용 대상 아님. 저장소 여부/검사 실패를 저장소 밖으로 오인하지 않는다. 기존 `.gitignore`는 보존한다.
- `config check`는 `provider`, 모델, 키의 configured 여부, 권한/Git 보호 여부만 출력한다. 키의 앞뒤 일부·길이·해시도 출력하지 않는다. 조회만 하며 파일을 생성하지 않는다.
- 키 객체는 `repr=False` 필드로 두고 generic dataclass 직렬화 경로에 전달하지 않는다. 공급자 raw exception/headers/body를 사용자 출력에 포함하지 않는다.
- `OPENAI_BASE_URL` 등 암묵 환경 설정으로 키가 다른 서버로 전송되지 않도록 공식 HTTPS endpoint를 명시한다. 사용자 지정 endpoint와 조직/project override는 이번 범위에서 지원하지 않는다.
- 최종 코드 리뷰 반영: SDK 2.48은 `OPENAI_CUSTOM_HEADERS`로 Authorization/조직/project/Host를 덮어쓸 수 있다. 이 환경변수가 비어 있지 않으면 실제 생성의 Run 생성 전에 고정 오류로 거부한다. 직접 어댑터 실행에서도 SDK 할당 직전에 다시 검사한다. 전역 환경을 자동 수정하거나 값을 출력하지 않으며, 저장된 결과 조회는 계속 가능하다.

### API와 실행 계약

- Responses API의 strict JSON schema 출력, `store=False`, `stream=True`, `max_retries=0`를 사용한다. SDK import/client 생성은 모델 실행이 실제 필요할 때만 한다.
- `instructions`는 앱의 Framing prompt, `input`은 seed와 저장된 QA의 JSON 텍스트만 포함한다. 임의 로컬 파일·키·Run 전체 이력을 전송하지 않는다. tools/background/previous_response_id는 사용하지 않는다.
- `framing.control` / `framing.propose`만 허용한다. 모델명·토큰 한도·timeout은 RunRequest에서 취한다. reasoning effort는 이번 신규 연결에서 강제하지 않는다. 기존 prototype prompt/모델 설정은 수정하지 않는다.
- SDK에 보내는 schema는 지원되는 부분집합으로 변환한다. `uniqueItems`는 전송 schema에서 제거하고 나머지 지원 여부도 공식 문서/SDK에서 확인한다. 로컬 `validate_questions`/`validate_frame`는 원래 엄격한 계약을 유지한다. 서버 스키마가 로컬 검증을 대체하지 않는다.
- `response.output_text.delta`의 실제 텍스트만 progress로 전달한다. 빈 문자열/공백뿐인 delta는 progress에서 건너뛰어 기존 RunSignal의 nonblank 계약을 지킨다. 완성 JSON은 delta를 이어붙인 값이 아니라 최종 응답 텍스트로 파싱하므로 공백 생략으로 손상되지 않는다. 가짜 heartbeat를 만들지 않는다. SDK의 최종 `response.completed` 객체에서 output/usage를 추출한다. 출력 첫 조각을 성공으로 처리하지 않는다.
- completed output에서 reasoning item은 파싱/저장하지 않고 무시한다. message의 output_text만 순서대로 결합한다. refusal content는 failed이며 tool call/기타 미지원 output item도 failed다. 빈 최종 텍스트, incomplete/failed/error/예외/중간 EOF는 failed이며 성공 proposal을 만들지 않는다. JSON은 중복 키·NaN·비객체를 거부한다.
- 제공된 최종 input/output tokens만 known으로 기록하고 cost/price_ref는 null이다. JSON 파싱 실패나 거절에서도 확인된 usage를 먼저 보존한다. 누락 usage는 unknown이며 임의 추산하지 않는다.
- provider_request_id에는 SDK의 HTTP request ID를 사용한다. Response 객체의 `id`와 혼용하지 않는다. SSE에서 HTTP ID를 얻지 못하면 null을 유지한다. 오류 ID도 검증된 값만 사용한다.
- SDK 예외는 인증/권한/요청 제한/연결/timeout/provider/invalid-output 같은 고정 reason 코드로 매핑한다. 원문 오류와 인증정보는 로그에 남기지 않는다.
- stream과 SDK client는 finally에서 닫는다. 취소·timeout은 기존 협조적 경계를 유지한다. transport timeout은 최대 요청 timeout, read timeout은 min(10초, 요청 timeout)로 설정한다. 전체 경과는 Runner deadline으로 검사하되 DNS/OS 지연까지 정확한 강제 종료를 보장한다고 쓰지 않는다.
- 사용자의 중단 후 자동 재호출하지 않는다. RunStarted 이후 중단 복구와 원자적 success/cancellation hook은 그대로 사용한다. 키 누락 같은 사전 설정 실패는 Run을 만들지 않는다.

## Task 1 — 프로젝트 전용 설정과 보호

**Files:** 생성 `inquiry/config.py`, `tests/test_config.py`, 루트 `requirements.txt`, `.env.example`; 수정 `inquiry/cli.py`, `inquiry/README.md`. 기존 `.env.example`이 있으면 내용을 보존하여 추가하고 실제 `.env`는 수정하지 않는다.

**Interfaces:** `load_openai_settings(root, *, model=None) -> OpenAISettings`; `OpenAISettings`는 `api_key`(repr 제외), `model`을 가진다. `check_config(root, *, model=None) -> dict`는 비밀 없는 상태만 반환한다. 앱이 관리하는 `ConfigError(ValueError)` 메시지는 고정 문구다.

- [x] RED: `tests/test_config.py`에서 임시 root/parent의 서로 다른 키, 환경 키, 빈 설정, 중복, interpolation 문자열, symlink, 0644, 다른 UID(fstat mock), tracked/unignored/Git 실패를 준비한다. root만 선택되고 비밀 문자열이 예외/stdout/stderr에 없음을 검사한다.
- [x] `python3 -m unittest tests.test_config -v` 실행: 모듈/함수 부재로 실패하는지 확인한다.
- [x] 표준 `os.open(..., O_RDONLY | O_NOFOLLOW)`와 `fstat`, 파일 객체를 이용해 안전하게 읽고, `dotenv_values(stream=..., interpolate=False)`로 파싱한다. 안전한 Git subprocess 검사는 shell=False로 실행하며 파일 내용은 인자로 넘기지 않는다.
- [x] `config check` CLI를 추가한다. 루트 requirements는 프로토타입과 같은 위 두 범위만 선언하고, README에는 수동 `.env` 편집·권한 수정·Git 제외·키 제거/교체 안내를 작성한다. 예시에는 합성 placeholder만 쓴다.
- [x] GREEN: 위 테스트와 `python3 -m unittest discover -s tests -q` 실행. SDK 없는 환경에서도 기존 조회/승인 테스트가 통과해야 한다.

## Task 2 — OpenAI adapter와 오프라인 transport 계약

**Files:** 생성 `inquiry/openai_adapter.py`, `tests/test_openai_adapter.py`; 기존 `inquiry/adapter.py` 계약을 소비한다. 필요시 SDK 전송용 schema 변환 함수는 새 adapter 파일에 둔다.

**Interfaces:** `OpenAIAdapter(settings, *, client_factory=None).run(request: RunRequest) -> Iterator[RunSignal]`. factory는 테스트에서 fake client/stream을 주입하고 production은 함수 내부에서 SDK를 import한다. adapter가 호출별 client/stream 소유권과 정리를 담당한다.

- [x] RED: fake factory가 받은 api_key/base_url/max_retries/timeout과 responses.create kwargs를 캡처한다. completed delta/usage, 공백 delta, reasoning+message, refusal, tool call, incomplete, failed, malformed JSON, duplicate keys, EOF, auth/rate-limit/timeout을 각각 고정 fixture로 제공한다.
- [x] `python3 -m unittest tests.test_openai_adapter -v`: 아직 adapter가 없어 실패하는지 확인한다.
- [x] 위 API 계약에 따라 신호를 매핑한다. terminal 이전에는 proposal을 만들지 않으며 local schema 검증은 기존 Framing success hook에 맡긴다. parsing 실패에도 실제 usage를 전달한다.
- [x] SDK 설치 환경에서 fake HTTP transport/SSE body로 실제 SDK event 객체 파싱도 검증한다. SDK 비설치 시 core 테스트는 통과하되 이 통합 테스트는 명시 skip으로 보고하고 연결 검증 완료로 계산하지 않는다.
- [x] GREEN: adapter/기존 runtime 테스트 실행. stream close 오류·중간 KeyboardInterrupt·시작 직후 종료를 주입하여 중복 과금 재시도나 부분 그래프 반영이 없는지 확인한다.

## Task 3 — CLI Framing 연결과 무호출 경로 보존

**Files:** 수정 `inquiry/cli.py`, `inquiry/framing.py`, `inquiry/README.md`, `tests/test_framing_flow.py`; 생성 `tests/test_openai_cli.py`. 기존 `tests/test_framing_process.py`, `tests/test_run_hooks.py` 회귀 실행.

**Interfaces:** `FramingService.advance(session_id, adapter=None, *, model='fake', regenerate=False, cancelled=None, adapter_factory=None, max_output_tokens=None, timeout=30.0)`로 확장한다. `adapter_factory() -> tuple[Adapter, str]`는 어댑터와 최종 모델명을 반환한다. 기존 positional adapter 주입은 유지하고, 둘을 동시에 주면 오류다. 저장된 상태 확인 후 실제 Run이 필요한 분기에서만 factory를 호출하고 반환된 모델명으로 RunRequest를 만든다. CLI closure가 `load_openai_settings(root, model=args.model)`을 호출하므로 키/모델 조회도 지연된다. factory 호출 후에도 Runner preflight가 최신 상태를 검증한다. done-control 뒤 frame 요청에서는 같은 factory와 제한을 넘긴다. 반환된 adapter를 다음 호출의 positional 인자로 동시에 넘기지 않는다.

- [x] RED: CLI `framing next`에서 미응답 질문/pending 제안/accepted 세션을 반환할 때 key loader와 SDK factory가 전혀 호출되지 않음을 spy로 검사한다. `show/resume/accept`도 동일하다.
- [x] 기존 `test_cli_injected_adapter_and_unconfigured_error`를 두 경우로 분리한다. 저장된 질문이 있으면 adapter 없이 성공해야 하며, 실제 새 질문 생성이 필요한 fresh session에서 설정이 없을 때만 SystemExit를 기대한다. 기존의 무조건 미설정 오류 기대는 새 무호출 계약으로 의도적으로 대체한다.
- [x] RED: 새 실행에서만 설정을 읽고 실제 model이 RunStarted에 들어감을 검사한다. 기존 `main(argv, adapter=fake)`는 키 없이 동작하고 model 기본 fake를 유지한다. production의 model은 CLI 기본 None → 프로젝트 설정이며 fake가 자동 선택되지 않는다.
- [x] `framing next --model <id> --max-output-tokens <n> --timeout <seconds>`를 연결한다. 둘 다 양의 유한 값이며 tokens는 정수다. override 없으면 기존 control 4000/propose 16000을 유지하고 timeout은 60초로 명시한다. service의 기존 호출 기본값은 유지하여 기존 테스트 의미를 바꾸지 않는다.
- [x] stderr에 첫 실제 실행 전 공급자·모델·관련 seed/QA 전송·토큰 상한·사용자 API 비용 안내를 출력한다. stdout은 기존 JSON이다. 자동 두 번째 frame 호출 가능성과 호출별 상한을 안내한다. 비용 추정액을 발명하지 않는다.
- [x] GREEN: CLI fake factory로 질문→답변→done→프레임→승인→재시작 여정, 잘못된 출력/취소/인증 실패/미종결 Run/저장 실패 시 경계 불변을 검사한다. 설정오류는 호출0/새Run0, 공급자 실패는 terminal 실패Run을 남긴다.

## Task 4 — 검증·리뷰·선택적 smoke

**Files:** 생성 `docs/reports/m2-4a-openai-eval.md`; 수정 `docs/MILESTONES.md`, `docs/superpowers/plans/2026-09-17-m2-implementation.md`는 실제 완료 범위만 반영한다.

- [ ] `python3 -m unittest discover -s tests -v`, `python3 -m compileall -q inquiry tests`, `git diff --check` 실행. key canary가 로그/CLI/errors/export 경로에 없음을 검증한다. 합성 사용자 내용에 키를 의도적으로 넣는 경우까지 자동 DLP를 보장하지 않는다.
- [ ] 독립 코드 리뷰에서 설정 격리·자격증명 처리·네트워크 대상·SDK 실제 파싱·무호출 재개·중단 복구를 점검한다. 지적 수정 후 재검증한다.
- [ ] 기본 보고서는 offline 완료/API smoke 미실시를 구분한다. 실제 smoke는 별도 허가 이후 합성 seed+사람이 작성한 합성 답변, 최대5회(control최대3 + frame1 + 여유1), 호출별4000 tokens/60초, 재시도0으로 한정한다. 실패/한도 소진 시 중단하고 추가 호출은 다시 범위를 결정한다. 금액 hard cap이라고 표현하지 않는다.
- [ ] smoke에서는 모델명을 사용자가 지정한다. 질문3~5개·구조화된 후보·승인 후 suggested·재시작 유지·실측 usage를 확인한다. 호출/토큰/unknown 수를 보고하고, 실제 사람 UX와는 구별한다. 실키·원본 provider exception은 보고서에 넣지 않는다.

## 계획 자체 점검

확정된 제품 방향은 변경하지 않았다. 키는 프로젝트 `.env` 수동 관리로 범위를 제한했고, OS 저장소/키 자동 변경/다중 공급자/패키징은 제외했다. 실제 비용 발생 실행은 이번 작업의 완료 조건으로 강제하지 않는다. 신규 파일명은 구현 대상이며 존재한다고 주장하지 않는다. 현재 변경은 문서뿐이다.

## 공식 참조 (2026-09-20 확인)

- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs): strict schema와 거절/지원 범위. 로컬 계약과 공급자 schema를 구분한다.
- [Responses streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events): delta와 completed/failed/incomplete를 구분한다.
- [Data controls](https://developers.openai.com/api/docs/guides/your-data): `store=False`를 공급자의 모든 보관이 없다는 약속으로 설명하지 않는다.

**상태:** 2026-09-20 critic 재검토 **OKAY**, 남은 차단 이슈 없음. [검토 기록](../../reports/m2-4a-plan-review.md). Task 1~3 구현·단계별 리뷰 완료. 전체 리뷰의 SDK 환경 헤더 격리 보완 중이며 실제 API 호출·커밋·푸시는 미실시.

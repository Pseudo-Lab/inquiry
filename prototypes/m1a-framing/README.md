# M1a — Framing Session 단독 검증

> 관련: [`docs/MILESTONES.md`](../../docs/MILESTONES.md) M1a · [`docs/REVIEW.md`](../../docs/REVIEW.md) 부록 C-0a · 원문 §7 · [ADR-D4](../../docs/decisions/ADR-D4-agent-adapter.md)

막연한 입력 → 3~5회 적응형 Q&A → **탐구 프레임(텍스트)** 생성만 검증한다.
그래프·TUI·저장·상태 머신은 **의도적으로 없다**. 여기서 검증하는 건 오직 프롬프트 품질이다.

## 무엇을/왜

이 단계는 제품의 **첫인상 급소**다. Framing이 안 되면 나머지(M2 코어, M3 OSS)는 의미가 없다.
그래서 가장 싸게 — 코드 인프라 없이 프롬프트만 — 먼저 검증한다.

- 구현 언어: Python (M0 확정)
- 모델: `gpt-6-astra` (ADR-D4 2026-09-10 변경), OpenAI Responses API. 프레임 생성은 reasoning effort high.
- 산출물: stdout / `--out` 파일. DB·그래프 없음.

## 실행

```bash
cd prototypes/m1a-framing
python3 -m venv out/venv
source out/venv/bin/activate
python -m pip install -r requirements.txt
# 프로젝트 루트 .env 파일의 OPENAI_API_KEY= 뒤에 키를 입력한다.

# 대화형 — 직접 생각을 입력하고 질문에 답한다
python framing.py

# 번들 샘플 시드로 대화형
python framing.py --sample research

# 샘플 + 응답까지 LLM이 자동 (빠른 눈검사)
python framing.py --sample policy --simulate

# 5종 전부 자동 실행 → Exit 게이트 한 번에 점검
mkdir -p out
set -o pipefail
python -u framing.py --all --simulate --out out/frame.md | tee out/session.log

# 임의 입력
python framing.py "만약 에이전트가 항상 자기 판단 근거를 설명할 수 있다면?"
```

키는 https://platform.openai.com/api-keys 에서 발급한 OpenAI API 키를 사용한다.
프로젝트 루트 `.env`의 `OPENAI_API_KEY`를 자동으로 읽는다. `export`는 필요 없다.
프로젝트 키가 우선이며, 키가 비어 있으면 기존 환경변수를 사용한다.
실행 위치에 관계없이 이 프로젝트의 `.env`만 읽고 환경변수는 변경하지 않는다.
`.env`는 Git에서 제외하며, 공유용 빈 양식은 `.env.example`이다.
ChatGPT/Codex 로그인만으로는 이 스크립트가 인증되지 않는다.
`--model`로 접근 가능한 다른 Responses/structured outputs/reasoning 지원 모델을 지정할 수 있다.
출력 토큰 한도에는 reasoning 토큰도 포함되므로 질문·모의 답변은 4,000, 프레임은 16,000으로 설정했다.
미완료 또는 텍스트 없는 응답은 오류로 처리한다.

API 키 없는 연동 검사: `python -m unittest discover -s . -v`.
이는 HTTP 모의 응답을 사용하므로 실제 모델 품질 검증을 대신하지 않는다.
실제 판정에서는 `out/session.log`의 질문·답변과 `out/frame-*.md`를 함께 읽는다.
최종 Exit 전에 실제 사람이 답하는 대화형 세션 1~2개도 필요하다.

질문 전에 이번 질문이 필요한 이유와 남은 최대 문항 수를 표시한다.
새 대화는 총 3~5문항이며, 라운드 수 때문에 2문항에서 종료하던 문제는 수정했다.

## 기존 답변으로 이어가기

기존 대화를 새 시드로 요약해 다시 시작하지 말고 Q&A 이력으로 전달한다.
`--history-file`은 아래 JSON 파일을 읽으며, 다른 시드 옵션·`--all`과 함께 쓰지 않는다.

```json
{
  "seed": "처음 입력한 생각",
  "rounds": [
    {"questions": ["실제로 물었던 질문"], "answer": "실제 사용자 답변"}
  ]
}
```

```bash
python framing.py --history-file out/history.json --out out/frame-resumed.md
```

질문 수는 기존 이력까지 합쳐 최대 5개다. 이미 5개에 답했다면 추가 질문 없이
기존 답변으로 프레임을 만든다. 미정 사항은 결과에 남긴다.
이력 파일은 자동 저장되지 않으며 기존 Q&A를 위 형식으로 전달해야 한다.
개인적인 답변이 담긴 이력은 Git에서 제외되는 `out/`에 보관한다.

## 5종 입력 (Exit 기준이 요구하는 테스트 세트)

`samples/` 에 부록 C-0a가 명시한 5종이 들어 있다:

| 이름 | 유형 |
|---|---|
| `research` | 연구 질문 |
| `product` | 제품 아이디어 |
| `policy` | 정책/의사결정 |
| `creative` | 창작 아이디어 |
| `thought-experiment` | 순수 사고실험 |

## Exit 기준 판정 (REVIEW 부록 C-0a)

`--all --simulate` 출력을 사람이 읽고 아래 3가지를 판정한다. 통과해야 M1b/M2로 간다.

1. **질문이 유도적이지 않고, 3~5문항 안에 프레임이 잡힌다.**
   - 질문이 답을 문장에 심고 있지 않은지, 총 3~5개인지 확인.
2. **5종 모두에서 "중심 질문 + 판단 기준 + 범위"가 사람이 보기에 타당.**
   - 프레임의 `## 중심 질문` / `## 판단 기준` / `## 탐구 범위와 비범위` 3개 항목 품질.
3. **초기 가설 후보가 서로 성격이 다르게(중복 아님) 나온다.**
   - `## 초기 가설 후보`가 같은 말의 재탕이 아니라 서로 다른 축인지.

실패 시: 여기서 멈추고 프롬프트(이 스크립트의 `FACILITATOR_SYSTEM` / `FRAMER_SYSTEM`)를
고쳐 다시 돌린다. 프레이밍이 안 되면 제품 전체를 재검토한다.

## 스코프 밖 (지금 하지 않음)

- 그래프/DAG, 상태 머신(D5), 이벤트 로그(D1) — M2에서 처음 코드화
- confidence 점수/provenance(D3) — 후속. 여기 가설은 `[suggested]` 후보일 뿐 점수 없음
- 비용 회계/spend cap(D6), TUI(M1b)

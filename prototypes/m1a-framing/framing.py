#!/usr/bin/env python3
"""M1a — Framing Session 단독 검증 프로토타입.

막연한 입력 → 3~5회 적응형 Q&A → 탐구 프레임(텍스트) 생성.
그래프·TUI·저장은 전부 없다 (REVIEW 부록 C-0a / MILESTONES M1a).

검증 대상은 오직 **프롬프트 품질**이다:
  - 질문이 유도적이지 않고 3~5문항 안에 프레임이 잡히는가
  - 5종 입력(연구/제품/정책/창작/사고실험)에서 "중심 질문 + 판단 기준 + 범위"가 타당한가
  - 초기 가설 후보가 서로 성격이 다른가(중복 아님)

구현 대상 모델: OpenAI (ADR-D4, 2026-09-10 변경). 기본 gpt-6-astra.

사용:
    export OPENAI_API_KEY=...
    python framing.py                       # 대화형(직접 입력)
    python framing.py --sample research     # 샘플 시드로 대화형
    python framing.py --sample research --simulate   # 응답까지 LLM이 자동
    python framing.py --simulate --all      # 5종 전부 자동 실행(Exit 게이트 점검)
    python framing.py --out frame.md "막연한 생각..."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

try:
    from openai import OpenAI
    from dotenv import dotenv_values
except ImportError:
    sys.exit("의존성 설치가 필요합니다:  pip install -r requirements.txt")

DEFAULT_MODEL = "gpt-6-astra"
MIN_QUESTIONS = 3
MAX_QUESTIONS = 5

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLE_NAMES = ["research", "product", "policy", "creative", "thought-experiment"]

# ---------------------------------------------------------------------------
# 시스템 프롬프트
# ---------------------------------------------------------------------------

# 진행자(facilitator): 적응형 질문을 만들고 언제 멈출지 판단한다.
FACILITATOR_SYSTEM = """\
너는 Inquiry의 Framing Session 진행자다. 사용자는 완성된 질문이 아니라 막연한
생각 한 덩어리를 던진다. 너의 일은 최소한의 적응형 질의응답으로 탐구 프레임을
잡을 수 있을 만큼의 정보를 끌어내는 것이다.

핵심 원칙:
- 가설(가능성)이 기본 단위다. 사용자의 불확실성을 억지로 제거하지 말고, 탐구
  가능한 형태로 바꾼다.
- 에이전트의 확신을 진실처럼 표현하지 않는다. 답을 유도하지 않는다.
- 사람이 탐구의 경계(비용·시간·범위·판단 기준)를 가진다. 그것을 대신 정하지 말고 묻는다.

질문 규칙 (매우 중요):
- **유도적이지 않게.** 특정 답을 전제하거나 답을 문장 안에 심지 말 것. 개방형으로.
- 기본 3문항의 취지를 시드에 맞게 자연스럽게 바꿔 묻는다:
    1) 무엇을 알고 싶거나 바꾸고 싶은가?
    2) 이 탐구 결과를 실제로 어떤 결정이나 산출물에 쓸 것인가?
    3) 무엇을 확인하면 "성립한다/충분하다"고 판단할 수 있는가?
- 현재 믿음, 반증 조건, 시간·비용·대상 범위는 **답변에 꼭 필요할 때만** 후속 질문으로 묻는다.
- 전체 질문 수는 3~5개를 넘기지 않는다. 기본 3문항으로 충분하면 후속 질문을 하지 않는다.
- 한 라운드에 너무 많이 쏟아내지 말 것. 각 질문은 한 문장.
- 질문은 전문 용어나 추상적인 평가 표현 없이, 사용자가 겪은 장면이나 원하는 결과를
  짧게 말할 수 있는 일상어로 쓴다. 한 문장에 여러 과제를 묶지 않는다.
- 창작 입력에서는 기본 세 취지를 구체적인 경험·궁금한 장면, 독자와 글의 쓰임,
  글에 담기면 유용하겠다고 느끼는 내용으로 풀어 묻는다. 독자에게 줄 변화나
  독창성의 판정 기준을 처음부터 정의하게 하지 않는다.
- 쉬운 질문을 만든다는 이유로 답변 후보나 해결책을 질문 안에 나열하지 않는다.
  사용자가 모른다고 하면 그것을 허용하고, 이미 말한 사실부터 좁혀 묻는다.
- 기존 Q&A가 없는 새 대화의 첫 라운드에는 기본 세 취지를 다루는 질문을 3개 묻고, 이후에는 필요한
  후속 질문만 1~2개 묻는다. 이전 질문과 답변을 세어 총 5문항을 넘기지 않는다.
- 기존 Q&A가 있으면 그 답변을 그대로 이어받는다. 이미 정한 주제·독자·목적·방법을
  다시 묻거나 단지 더 자세한 사례를 모으려고 질문을 늘리지 않는다.

종료 판단:
- 답변에서 탐구의 초점, 결과의 쓰임(순수 탐색도 가능), 무엇을 얻으면 충분한지가
  드러나는지 확인한다. 사용자가 이미 말한 내용은 다시 확인받지 않는다.
- 창작에서 독자나 넣고 싶은 소재만 말한 것은 충분성 기준과 다를 수 있다.
  충분성이 아직 없으면 남은 질문으로 독자가 글에서 무엇을 알아가거나 해볼 수 있길
  바라는지 쉬운 말로 묻는다. 사용자의 답에 기대어 질문하며 답을 대신 제시하지 않는다.
- 주제가 여러 갈래면 우선 다룰 것, 충분성이 없으면 원하는 결과를 후속 1~2문항에
  우선 배정한다. 이 정보가 부족한데 소재를 더 모으는 질문만 하고 끝내지 않는다.
- 정성적인 설명도 충분성 기준이 될 수 있다. 숫자나 실험 설계는 해당 탐구에
  꼭 필요하지 않으면 요구하지 않는다. 5문항 뒤에도 모르는 부분은 미정으로 남긴다.

모드: 첫 입력을 바탕으로 하나를 추천한다(사용자가 고르지 않아도 된다).
- explore : 새로운 가능성을 넓게 찾고 더 깊이 이해
- decide  : 여러 가능성을 비교해 선택을 도움
- test    : 특정 가능성이 실제로 성립하는지 확인

너는 매 턴 반드시 지정된 JSON 스키마로만 응답한다.
- done=false 이면 questions에 이번 라운드에 물을 질문(1~3개)을 담는다.
- question_rationale에는 이번에 꼭 필요한 빈칸이 무엇이고 왜 묻는지 사용자가 이해할
  한 문장을 쓴다. 검증 실험을 시키거나 특정 답변을 유도하지 않는다. done=true면 빈 문자열.
- 충분한 정보가 모였으면 done=true, questions=[] 로 응답한다.
"""

CONTROL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["explore", "decide", "test"]},
        "mode_rationale": {
            "type": "string",
            "description": "이 모드를 추천하는 한 문장 이유",
        },
        "done": {
            "type": "boolean",
            "description": "프레임을 만들기에 충분한 정보가 모였는가",
        },
        "question_rationale": {"type": "string", "description": "이번 질문이 필요한 이유를 쉬운 한 문장으로 설명"},
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "이번 라운드에 물을 질문(done=true면 빈 배열)",
        },
    },
    "required": ["mode", "mode_rationale", "done", "question_rationale", "questions"],
    "additionalProperties": False,
}

# 프레임 생성기: 대화 전체를 받아 최종 프레임(마크다운)을 출력한다.
FRAMER_SYSTEM = """\
너는 Inquiry의 Framing Session 결과를 정리하는 작성자다. 지금까지의 대화(막연한
입력 + 적응형 Q&A)를 근거로 **탐구 프레임**을 마크다운으로 작성한다.

반드시 아래 8개 항목을 순서대로, 각 항목 제목을 그대로 써서 작성한다. 대화에서
근거가 부족한 항목은 지어내지 말고 "(아직 미정 — 후속 확인 필요)"로 남긴다.

## 중심 질문
하나의 명료한 탐구 질문. 예/아니오로 닫히지 않아도 되지만 초점이 분명해야 한다.

## 탐구 목적
무엇을 알고 싶거나 바꾸고 싶은가.

## 사용 맥락 / 결정 대상
이 결과를 실제로 어떤 결정이나 산출물에 쓸 것인가.

## 현재 믿음
사용자가 지금 기울어 있는 잠정적 견해(있다면). 확신으로 포장하지 말 것.

## 판단 기준
무엇을 확인하면 "성립/충분/실패"라고 판단할지. 가능하면 관찰 가능한 형태로.
사용자가 말한 정성적인 충분성도 유효한 기준으로 정리한다. 창작에서는 글이 독자에게
무엇을 설명하거나 할 수 있게 해주면 충분한지와, 글에 소개할 방법의 효과가 입증됐는지를
구분한다. 전자의 기준이 있는데 후자의 실험 수치가 없다는 이유로 전부 미정으로 만들지
않는다. 사용자가 기준을 말하지 않았다면 발명하지 말고 미정으로 남긴다. 순수 사고실험이나
경험담에 실증·정량 기준이 필요하다고 강요하지 않는다.

## 탐구 범위와 비범위
무엇을 다루고 무엇을 명시적으로 다루지 않는가(시간·비용·대상 포함, 알 수 있는 만큼).

## 아직 열린 질문
프레이밍 후에도 남은 미해결 질문.

## 초기 가설 후보
서로 **성격이 다른** 가능성 2~4개. 각 항목은:
- 상태 `[suggested]`(회색 제안 상태 — 아직 활성화 아님)
- 한 줄 제목
- 한 문장 claim
- 다른 후보와 무엇이 다른지(축/관점) 한 구절
가설끼리 사실상 같은 말의 재탕이면 안 된다. 낙관/비관, 원인/대안설명, 좁은/넓은
범위 등 서로 다른 축을 잡을 것. 여기서는 confidence 점수를 매기지 않는다(후속 단계).
"""


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _first_text(response) -> str:
    if response.status != "completed":
        raise RuntimeError(f"모델 응답이 완료되지 않았습니다: {response.status}")
    if not response.output_text.strip():
        raise RuntimeError("모델이 텍스트를 반환하지 않았습니다(거절 또는 빈 응답).")
    return response.output_text


def control_turn(client, model, messages) -> dict:
    """진행자 턴: 다음 질문 또는 완료 신호를 JSON으로 받는다."""
    response = client.responses.create(
        model=model,
        max_output_tokens=4000,
        reasoning={"effort": "low"},
        instructions=FACILITATOR_SYSTEM,
        input=messages,
        text={"format": {"type": "json_schema", "name": "framing_control",
                         "strict": True, "schema": CONTROL_SCHEMA}},
        store=False,
    )
    return json.loads(_first_text(response))


def frame_turn(client, model, transcript: str) -> str:
    """프레임 생성 턴: 최종 프레임 마크다운을 받는다."""
    response = client.responses.create(
        model=model,
        max_output_tokens=16000,
        reasoning={"effort": "high"},
        instructions=FRAMER_SYSTEM,
        input=[{"role": "user", "content": transcript}],
        store=False,
    )
    return _first_text(response).strip()


def simulate_answer(client, model, seed: str, questions: list[str]) -> str:
    """검증용: 시드 맥락에 맞는 그럴듯한 사용자 답변을 LLM이 생성한다."""
    q_block = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    prompt = textwrap.dedent(
        f"""\
        너는 아래의 막연한 생각을 던진 사용자 역할이다. 진행자의 질문에 사용자로서
        간결하고 현실적으로 답하라. 아직 정리 안 된 사람처럼, 다 알지는 못하는 채로
        답해도 된다. 질문마다 1~3문장.

        [내 생각]
        {seed}

        [질문]
        {q_block}
        """
    )
    response = client.responses.create(
        model=model,
        max_output_tokens=4000,
        reasoning={"effort": "low"},
        input=[{"role": "user", "content": prompt}],
        store=False,
    )
    return _first_text(response).strip()


# ---------------------------------------------------------------------------
# 세션 진행
# ---------------------------------------------------------------------------


def validate_rounds(rounds) -> int:
    """재개 이력은 답변까지 끝난 질문 묶음만 허용한다."""
    if not isinstance(rounds, list):
        raise ValueError("rounds는 질문·답변 묶음의 배열이어야 합니다.")
    count = 0
    for item in rounds:
        if not isinstance(item, dict):
            raise ValueError("각 이력은 questions와 answer를 포함해야 합니다.")
        questions, answer = item.get("questions"), item.get("answer")
        if (not isinstance(questions, list) or not questions
                or any(not isinstance(q, str) or not q.strip() for q in questions)
                or not isinstance(answer, str) or not answer.strip()):
            raise ValueError("이력에는 비어 있지 않은 questions 배열과 answer 문자열이 필요합니다.")
        count += len(questions)
    if count > MAX_QUESTIONS:
        raise ValueError("이력의 총 질문 수는 5개를 넘을 수 없습니다.")
    return count


def run_session(client, model, seed: str, simulate: bool, rounds=None) -> str:
    rounds = [] if rounds is None else rounds
    asked = validate_rounds(rounds)
    messages = [
        {
            "role": "user",
            "content": f"[막연한 생각]\n{seed}\n\n이걸 탐구 프레임으로 잡고 싶어.",
        }
    ]
    for item in rounds:
        messages.append({"role": "assistant", "content": _questions_as_text(item["questions"])})
        messages.append({"role": "user", "content": item["answer"]})
    round_no = len(rounds)
    mode_shown = False

    print("\n답변을 바탕으로 탐구할 질문·범위·판단 기준을 정리합니다. 실제 글 작성이나 실험을 요구하지 않습니다.")
    print(f"최대 {MAX_QUESTIONS}문항 중 기존 답변 {asked}개, 남은 질문 {MAX_QUESTIONS - asked}개. 모르는 부분은 미정으로 남길 수 있습니다.")
    while asked < MAX_QUESTIONS:
        control = control_turn(client, model, messages)

        if not mode_shown:
            print(f"\n추천 모드: {control['mode']}  — {control['mode_rationale']}")
            mode_shown = True

        remaining = MAX_QUESTIONS - asked
        if control["done"] and asked >= MIN_QUESTIONS:
            break

        questions = [q for q in control["questions"] if q.strip()]
        if not questions:
            # 아직 최소 문항에 못 미치는데 질문이 비었으면 한 번 더 유도
            if asked >= MIN_QUESTIONS:
                break
            questions = ["무엇을 확인하면 이 탐구가 성공했다고 판단할 수 있을까요?"]

        # 남은 한도 안으로 자른다 (총 3~5 유지)
        questions = questions[:remaining]
        round_no += 1

        print(f"\n── 질문 라운드 {round_no} ──")
        print(control["question_rationale"])
        print(f"이번 {len(questions)}문항 · 답변 후 추가 질문은 최대 {remaining - len(questions)}개")
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q}")

        if simulate:
            answer = simulate_answer(client, model, seed, questions)
            print("\n[모의 응답]")
            print(textwrap.indent(answer, "  "))
        else:
            print("\n(각 질문에 이어서 답해주세요. 빈 줄로 이 라운드 종료)")
            lines = []
            for i in range(len(questions)):
                try:
                    ans = input(f"  답 {i+1}> ").strip()
                except EOFError:
                    ans = ""
                if ans:
                    lines.append(f"{i+1}. {ans}")
            answer = "\n".join(lines) or "(답변 없음 — 모르겠음)"

        asked += len(questions)
        messages.append({"role": "assistant", "content": _questions_as_text(questions)})
        messages.append({"role": "user", "content": answer})

    print(f"\n질문을 마쳤습니다(누적 {asked}문항). 기존 답변으로 프레임을 정리합니다.")
    transcript = _build_transcript(seed, messages)
    return frame_turn(client, model, transcript)


def _questions_as_text(questions: list[str]) -> str:
    return "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))


def _build_transcript(seed: str, messages) -> str:
    parts = [f"[막연한 입력]\n{seed}\n", "[Q&A 기록]"]
    # 첫 user 메시지는 시드이므로 건너뛴다.
    for m in messages[1:]:
        role = "진행자" if m["role"] == "assistant" else "사용자"
        parts.append(f"\n{role}:\n{m['content']}")
    parts.append("\n\n위 대화를 근거로 탐구 프레임을 작성하라.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 입력 해석 & main
# ---------------------------------------------------------------------------


def load_seed(args) -> str:
    if args.seed_text:
        return " ".join(args.seed_text).strip()
    if args.seed_file:
        return Path(args.seed_file).read_text(encoding="utf-8").strip()
    if args.sample:
        return _read_sample(args.sample)
    # 대화형 입력
    print("완성된 질문일 필요가 없습니다. 지금 떠오르는 생각을 적어주세요.")
    print("(여러 줄 가능, 빈 줄로 종료)\n")
    lines = []
    while True:
        try:
            line = input("❯ " if not lines else "  ")
        except EOFError:
            break
        if not line.strip() and lines:
            break
        if line.strip():
            lines.append(line)
    return "\n".join(lines).strip()


def _read_sample(name: str) -> str:
    path = SAMPLES_DIR / f"{name}.txt"
    if not path.exists():
        sys.exit(f"샘플 '{name}' 없음. 사용 가능: {', '.join(SAMPLE_NAMES)}")
    return path.read_text(encoding="utf-8").strip()


def api_key() -> str:
    """프로젝트 .env만 읽고, 전역 환경변수는 변경하지 않는다."""
    config = dotenv_values(Path(__file__).resolve().parents[2] / ".env", interpolate=False)
    return (config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")).strip()


def main():
    parser = argparse.ArgumentParser(
        description="M1a Framing Session 프로토타입 (프롬프트 품질 검증)"
    )
    parser.add_argument("seed_text", nargs="*", help="막연한 생각(따옴표로 감싸도 됨)")
    parser.add_argument("--sample", choices=SAMPLE_NAMES, help="번들 샘플 시드 사용")
    parser.add_argument("--seed-file", help="시드를 파일에서 읽기")
    parser.add_argument("--history-file", help="기존 seed와 rounds(questions/answer)가 담긴 JSON으로 이어가기")
    parser.add_argument(
        "--simulate", action="store_true", help="사용자 답변을 LLM이 자동 생성"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="5종 샘플 전부 실행 (--simulate 권장, Exit 게이트 점검)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"기본 {DEFAULT_MODEL}")
    parser.add_argument("--out", help="프레임을 파일로 저장")
    args = parser.parse_args()

    rounds = None
    if args.history_file:
        if args.all or args.sample or args.seed_file or args.seed_text:
            parser.error("--history-file은 다른 시드 옵션이나 --all과 함께 쓸 수 없습니다.")
        try:
            history = json.loads(Path(args.history_file).read_text(encoding="utf-8"))
            if not isinstance(history, dict) or not isinstance(history.get("seed"), str) or not history["seed"].strip():
                raise ValueError("history에 비어 있지 않은 seed 문자열이 필요합니다.")
            rounds = history["rounds"]
            validate_rounds(rounds)
        except (OSError, ValueError, KeyError) as error:
            parser.error(f"이력을 읽을 수 없습니다: {error}")

    key = api_key()
    if not key:
        sys.exit("프로젝트 루트 .env의 OPENAI_API_KEY를 입력해주세요.")
    client = OpenAI(api_key=key)

    if args.all:
        if not args.simulate:
            print("주의: --all 은 --simulate 와 함께 쓰는 것을 권장합니다.\n")
        for name in SAMPLE_NAMES:
            seed = _read_sample(name)
            print("\n" + "=" * 70)
            print(f"[샘플: {name}]  {seed[:60]}...")
            print("=" * 70)
            frame = run_session(client, args.model, seed, args.simulate)
            print("\n" + frame)
            if args.out:
                out = Path(args.out)
                target = out.with_name(f"{out.stem}-{name}{out.suffix or '.md'}")
                target.write_text(frame + "\n", encoding="utf-8")
                print(f"\n→ 저장: {target}")
        return

    seed = history["seed"] if args.history_file else load_seed(args)
    if not seed:
        sys.exit("입력이 비어 있습니다.")

    print("\n" + "=" * 70)
    print("프레이밍 진행 중...")
    print("=" * 70)
    frame = run_session(client, args.model, seed, args.simulate, rounds)
    print("\n" + "=" * 70)
    print("탐구 프레임")
    print("=" * 70 + "\n")
    print(frame)

    if args.out:
        Path(args.out).write_text(frame + "\n", encoding="utf-8")
        print(f"\n→ 저장: {args.out}")


if __name__ == "__main__":
    main()

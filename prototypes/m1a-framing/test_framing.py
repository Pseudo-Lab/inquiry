"""OpenAI API 경계 검증. 외부 요청이나 실제 API 키를 사용하지 않는다."""

import json
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import httpx
from openai import OpenAI

import framing


class SessionTests(unittest.TestCase):
    def history(self, n):
        return [{"questions": [f"질문 {i}" for i in range(n)], "answer": "기존 실제 답변"}]

    def test_five_previous_answers_skip_questions(self):
        with patch.object(framing, "control_turn") as control, patch.object(
            framing, "frame_turn", return_value="frame"
        ) as frame, redirect_stdout(io.StringIO()) as output:
            framing.run_session(None, "model", "seed", False, self.history(5))
            control.assert_not_called()
            self.assertIn("기존 실제 답변", frame.call_args.args[2])
            self.assertIn("남은 질문 0개", output.getvalue())

    def test_resumed_followup_counts_previous_questions(self):
        turn = {"mode": "explore", "mode_rationale": "탐색", "question_rationale": "범위를 좁히려고 묻습니다.", "done": False, "questions": ["추가1", "추가2", "초과"]}
        with patch.object(framing, "control_turn", return_value=turn) as control, patch.object(
            framing, "simulate_answer", return_value="추가 답변"
        ) as answer, patch.object(framing, "frame_turn", return_value="frame"), redirect_stdout(io.StringIO()) as output:
            framing.run_session(None, "model", "seed", True, self.history(3))
            self.assertEqual(control.call_count, 1)
            self.assertEqual(answer.call_args.args[3], ["추가1", "추가2"])
            self.assertIn("범위를 좁히려고", output.getvalue())

    def test_one_question_per_round_does_not_stop_at_two(self):
        turn = {"mode": "explore", "mode_rationale": "탐색", "question_rationale": "확인", "done": False, "questions": ["질문"]}
        done = dict(turn, done=True, questions=[])
        with patch.object(framing, "control_turn", side_effect=[turn, turn, turn, done]), patch.object(
            framing, "simulate_answer", return_value="답변"
        ) as answer, patch.object(framing, "frame_turn", return_value="frame"), redirect_stdout(io.StringIO()):
            framing.run_session(None, "model", "seed", True)
            self.assertEqual(answer.call_count, 3)

    def test_invalid_history_rejected_before_api(self):
        with patch.object(framing, "control_turn") as control:
            with self.assertRaises(ValueError):
                framing.run_session(None, "model", "seed", True, self.history(6))
            control.assert_not_called()


class ProjectKeyTests(unittest.TestCase):
    def test_project_key_takes_priority_without_changing_environment(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "shell-key"}), patch(
            "framing.dotenv_values", return_value={"OPENAI_API_KEY": "project-key"}, create=True
        ) as read:
            self.assertTrue(hasattr(framing, "api_key"), "프로젝트 키 로더 필요")
            self.assertEqual(framing.api_key(), "project-key")
            self.assertEqual(os.environ["OPENAI_API_KEY"], "shell-key")
            self.assertEqual(read.call_args.args[0], framing.Path(framing.__file__).resolve().parents[2] / ".env")

    def test_missing_project_key_falls_back_to_environment(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "shell-key"}), patch(
            "framing.dotenv_values", return_value={}, create=True
        ):
            self.assertTrue(hasattr(framing, "api_key"), "프로젝트 키 로더 필요")
            self.assertEqual(framing.api_key(), "shell-key")


class OpenAIBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.status = "completed"
        self.content = [{"type": "output_text", "text": "프레임", "annotations": []}]
        self.client = OpenAI(
            api_key="offline-test-key",
            http_client=httpx.Client(transport=httpx.MockTransport(self.respond)),
        )
        self.addCleanup(self.client.close)

    def respond(self, request):
        self.requests.append(json.loads(request.content))
        self.assertEqual(request.url.path, "/v1/responses")
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0,
            "model": "gpt-6-astra", "status": self.status,
            "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                        "status": "completed", "content": self.content}],
        })

    def test_control_uses_strict_schema_and_preserves_history(self):
        control = {"mode": "explore", "mode_rationale": "탐색", "done": False,
                   "question_rationale": "알고 싶은 것을 확인합니다.",
                   "questions": ["무엇을 알고 싶나요?"]}
        self.content[0]["text"] = json.dumps(control)
        history = [{"role": "user", "content": "생각"}]
        self.assertEqual(framing.control_turn(self.client, "gpt-6-astra", history), control)
        request = self.requests[0]
        self.assertEqual(request["input"], history)
        self.assertEqual(request["text"]["format"]["schema"], framing.CONTROL_SCHEMA)
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertFalse(request["store"])

    def test_frame_uses_high_reasoning_and_transcript(self):
        self.assertEqual(framing.frame_turn(self.client, "gpt-6-astra", "대화"), "프레임")
        self.assertEqual(self.requests[0]["reasoning"], {"effort": "high"})
        self.assertEqual(self.requests[0]["input"][0]["content"], "대화")

    def test_simulation_includes_seed_and_questions(self):
        self.assertEqual(framing.simulate_answer(self.client, "gpt-6-astra", "시드", ["질문"]), "프레임")
        prompt = self.requests[0]["input"][0]["content"]
        self.assertIn("시드", prompt)
        self.assertIn("질문", prompt)

    def test_incomplete_output_is_not_accepted_as_frame(self):
        self.status = "incomplete"
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            framing.frame_turn(self.client, "gpt-6-astra", "대화")

    def test_refusal_is_not_accepted_as_empty_frame(self):
        self.content = [{"type": "refusal", "refusal": "거절"}]
        with self.assertRaisesRegex(RuntimeError, "텍스트"):
            framing.frame_turn(self.client, "gpt-6-astra", "대화")


if __name__ == "__main__":
    unittest.main()

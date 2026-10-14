#!/usr/bin/env bash
# inquiry 데모 — 임시 폴더에 샘플 데이터를 깔고 바로 TUI를 띄운다(종료 시 자동 삭제).
#   ./scripts/demo.sh graph       사람 결정을 연습할 수 있는 가설 그래프
#   ./scripts/demo.sh bootstrap   에이전트 제안을 accept하는 흐름
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
export PYTHONPATH="$ROOT/src"
MODE="${1:-graph}"

if [ ! -x "$PY" ]; then
  echo "venv 파이썬이 없습니다: $PY  (venv 있는 worktree(puffin)에서 실행하세요)" >&2
  exit 1
fi

DIR="$(mktemp -d)"
trap 'rm -rf "$DIR"' EXIT   # 데모는 임시 — 종료 시 삭제

inq() { "$PY" -m inquiry --dir "$DIR" "$@"; }
mcp() { "$PY" -c "import sys; from inquiry import mcp_server as m; print(getattr(m, sys.argv[1])('$DIR', *sys.argv[2:]))" "$@"; }

if [ "$MODE" = "bootstrap" ]; then
  # 에이전트가 주제+frame 초안 제안 → TUI에서 사람이 accept
  "$PY" -c "from inquiry import mcp_server as m; m.propose_bootstrap('$DIR','claude-1','AI 코드리뷰 도구 수요','주니어 개발자가 월 구독료를 낼까?',purpose='유료 수요 검증',criteria=['인터뷰 5건 이상'])"
  echo ">> 데모(부트스트랩): 표에 뜬 'accept <BT-id>' 를 ':' 명령창에 입력해 inquiry를 생성해보세요."
else
  # 사람이 init → 에이전트가 가설 3개 + 근거 → 하나는 탐색 시작
  inq init --seed "AI 코드리뷰 도구 수요" --question "누가 돈 내고 쓸까?" >/dev/null
  H1="$("$PY" -c "from inquiry import mcp_server as m; print(m.add_hypothesis('$DIR','claude-1','유료 의향 있음','주니어는 시간 절약에 월 구독료를 낸다')['hypothesis_id'])")"
  "$PY" -c "from inquiry import mcp_server as m; print(m.add_hypothesis('$DIR','claude-1','조직 구매','결제 주체는 개발자가 아닌 플랫폼/보안 예산 소유자')['hypothesis_id'])" >/dev/null
  "$PY" -c "from inquiry import mcp_server as m; print(m.add_hypothesis('$DIR','claude-1','무료로 충분','기존 무료 도구로 충분해 지불 의향 낮음')['hypothesis_id'])" >/dev/null
  "$PY" -c "from inquiry import mcp_server as m; print(m.add_evidence('$DIR','claude-1','$H1','supports','human-interview','개발자 5명 중 3명이 유료 의향','2026-10-15T00:00:00Z'))" >/dev/null
  inq start "$H1" >/dev/null   # 하나는 exploring 으로(결정 연습 대상)
  echo ">> 데모(그래프): j/k로 가설 이동, ':' 후 start/support/contest/refute/close 로 결정해보세요."
fi

echo ">> (임시 폴더 $DIR — TUI 종료하면 자동 삭제됩니다)"
if [ -n "${DEMO_NO_TUI:-}" ]; then   # 검증용: TUI 없이 셋업만(폴더는 trap이 삭제)
  "$PY" -m inquiry --dir "$DIR" status >/dev/null && echo ">> 셋업 OK ($MODE)"
  exit 0
fi
exec "$PY" -m inquiry --dir "$DIR" tui

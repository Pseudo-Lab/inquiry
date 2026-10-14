# inquiry — 개발/검증 단축 명령.
#   긴 `python -m inquiry --dir ...` 대신 `make tui`, `make demo`, `make test` 로.
#   venv(.venv)가 있는 worktree(예: puffin)에서 실행하세요.
#
# 데이터 폴더: DIR (기본 $INQUIRY_DIR 또는 ~/inquiry-data). 덮어쓰기: `make tui DIR=/path`

# PY: 이 worktree의 .venv. venv가 다른 곳(예: puffin)이면 override:
#   make tui PY=/Users/minahkim/orca/workspaces/inquiry/puffin/.venv/bin/python
PY  ?= $(CURDIR)/.venv/bin/python
DIR ?= $(if $(INQUIRY_DIR),$(INQUIRY_DIR),$(HOME)/inquiry-data)
INQ := $(PY) -m inquiry --dir $(DIR)
export PYTHONPATH := $(CURDIR)/src

.DEFAULT_GOAL := help
.PHONY: help test tui demo demo-bootstrap status plan review list seed accept reject

help:  ## 명령 목록
	@echo "inquiry 단축 명령 (데이터 폴더 DIR=$(DIR))"
	@echo ""
	@echo "  make test            전체 테스트 실행"
	@echo "  make demo            샘플 가설 그래프를 깔고 바로 TUI (결정 연습용, 임시폴더)"
	@echo "  make demo-bootstrap  에이전트 제안을 깔고 바로 TUI (accept 연습용, 임시폴더)"
	@echo "  make tui             내 데이터 폴더로 TUI"
	@echo "  make status|plan|review|list   JSON/텍스트 뷰"
	@echo "  make seed TOPIC=\"주제\"         주제 seed"
	@echo "  make accept BID=BT-...         bootstrap 수락"
	@echo "  make reject BID=BT-... REASON=\"사유\""
	@echo ""
	@echo "  폴더 바꾸기:  make tui DIR=/Users/minahkim/inquiry-data"

test:  ## 전체 테스트
	$(PY) -m unittest discover -s tests

tui:  ## 내 데이터 폴더로 TUI 바로 실행
	$(INQ) tui

demo:  ## 샘플 그래프 + TUI (임시폴더, 종료 시 자동 삭제)
	@./scripts/demo.sh graph

demo-bootstrap:  ## 에이전트 제안 + TUI (임시폴더)
	@./scripts/demo.sh bootstrap

status:  ## 모니터 요약(JSON)
	$(INQ) status

plan:  ## NOW/NEXT/LATER
	$(INQ) plan --text

review:  ## 사람 결정 대기(JSON)
	$(INQ) review

list:  ## 대기 중 bootstrap 제안
	$(INQ) bootstrap list

seed:  ## 주제 seed:  make seed TOPIC="..."
	$(INQ) seed "$(TOPIC)"

accept:  ## bootstrap 수락:  make accept BID=BT-...
	$(INQ) bootstrap accept $(BID)

reject:  ## bootstrap 거부:  make reject BID=BT-... REASON="..."
	$(INQ) bootstrap reject $(BID) --reason "$(REASON)"

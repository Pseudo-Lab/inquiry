"""Local inquiry CLI with lazy, explicitly bounded provider generation."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import sys

from inquiry.commands import Commands
from inquiry.domain.events import EVIDENCE_TYPES
from inquiry.store.store import StoreError


_OPTIONAL_DEPENDENCIES = (
    'OpenAI support requires a compatible stable SDK and optional dependencies; '
    'install or upgrade from requirements.txt.'
)


def _require_openai_sdk():
    from importlib.metadata import PackageNotFoundError, version
    try:
        installed = version('openai')
    except PackageNotFoundError:
        raise ValueError(_OPTIONAL_DEPENDENCIES) from None
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', installed)
    if match is None or not ((2, 48, 0) <= tuple(map(int, match.groups())) < (3, 0, 0)):
        raise ValueError(_OPTIONAL_DEPENDENCIES)


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError('expected a positive integer') from None
    if str(parsed) != value.strip() or parsed <= 0:
        raise argparse.ArgumentTypeError('expected a positive integer')
    return parsed


def _positive_float(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError('expected a positive finite number') from None
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError('expected a positive finite number')
    return parsed


def _openai_factory(root, model, max_output_tokens, timeout, *, purpose='framing'):
    """Shared lazy binding for batch commands and the conversational entrypoint."""
    last_notice = None
    def create():
        nonlocal last_notice
        try:
            from inquiry.config import load_openai_settings
            from inquiry.llm.openai_adapter import OpenAIAdapter
        except ImportError:
            raise ValueError(_OPTIONAL_DEPENDENCIES) from None
        settings = load_openai_settings(root, model=model)
        _require_openai_sdk()
        adapter = OpenAIAdapter(settings)
        signature = (settings.model, max_output_tokens, timeout, purpose)
        if last_notice != signature:
            if purpose == 'branch':
                notice = ('NOTICE: OpenAI model {model} will receive the inquiry frame and '
                          'selected hypothesis content. Maximum output tokens per call: {limit}; '
                          'timeout {timeout:g}s. Branch generation makes one request. '
                          'OpenAI API usage may incur cost.').format(
                              model=settings.model, limit=max_output_tokens or 4000, timeout=timeout)
            elif purpose == 'deepen':
                notice = ('NOTICE: OpenAI model {model} will receive the inquiry frame and '
                          'selected hypothesis context. Maximum output tokens: {limit}; '
                          'timeout {timeout:g}s. Deepen generation makes one request. '
                          'OpenAI API usage may incur cost.').format(
                              model=settings.model, limit=max_output_tokens or 4000, timeout=timeout)
            elif purpose == 'challenge':
                notice = ('NOTICE: OpenAI model {model} will receive the inquiry frame and '
                          'selected hypothesis context. Maximum output tokens: {limit}; '
                          'timeout {timeout:g}s. Challenge generation makes one request. '
                          'OpenAI API usage may incur cost.').format(
                              model=settings.model, limit=max_output_tokens or 4000, timeout=timeout)
            elif purpose == 'synthesize':
                notice = ('NOTICE: OpenAI model {model} will receive the inquiry frame and selected '
                          'hypothesis contexts. Maximum output tokens: {limit}; timeout {timeout:g}s. '
                          'Synthesis generation makes one request. OpenAI API usage may incur cost.').format(
                              model=settings.model, limit=max_output_tokens or 4000, timeout=timeout)
            else:
                notice = ('NOTICE: OpenAI model {model} will receive the framing seed and '
                          'answered Q&A. Maximum output tokens per call: control {control}, '
                          'proposal {proposal}; timeout {timeout:g}s. A completed control '
                          'response may automatically trigger a second proposal call. '
                          'OpenAI API usage may incur cost.').format(
                              model=settings.model, control=max_output_tokens or 4000,
                              proposal=max_output_tokens or 16000, timeout=timeout)
            print(notice, file=sys.stderr)
            last_notice = signature
        return adapter, settings.model
    return create


def _generation_options(parser):
    parser.add_argument('--model')
    parser.add_argument('--max-output-tokens', type=_positive_int)
    parser.add_argument('--timeout', type=_positive_float, default=60.0)


def _relation(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--supports', action='store_true')
    group.add_argument('--challenges', action='store_true')


def main(argv=None, *, adapter=None):
    parser = argparse.ArgumentParser(
        description='Local Inquiry core with explicit human decisions and lazy provider generation.'
    )
    parser.add_argument('--dir', default='.', help='Inquiry directory')
    subs = parser.add_subparsers(dest='command', required=True)
    chat = subs.add_parser('chat', help='Interactive framing without copying IDs')
    _generation_options(chat)
    tui = subs.add_parser('tui', help='Textual map + explore operations')
    _generation_options(tui)
    branch = subs.add_parser('branch', help='Human-approved child hypothesis proposals')
    branch_subs = branch.add_subparsers(dest='operation', required=True)
    propose = branch_subs.add_parser('propose')
    propose.add_argument('parent_id')
    _generation_options(propose)
    branch_subs.add_parser('show').add_argument('proposal_id')
    accept = branch_subs.add_parser('accept')
    accept.add_argument('proposal_id')
    accept.add_argument('selected_ids', nargs='+')
    reject = branch_subs.add_parser('reject')
    reject.add_argument('proposal_id')
    reject.add_argument('--reason', required=True)
    branch_subs.add_parser('resume')
    explore = subs.add_parser('explore', help='Human-approved hypothesis operations')
    explore_subs = explore.add_subparsers(dest='operation', required=True)
    propose = explore_subs.add_parser('propose')
    propose.add_argument('kind', choices=('deepen', 'challenge', 'synthesize'))
    propose.add_argument('target_ids', nargs='+')
    _generation_options(propose)
    explore_subs.add_parser('show').add_argument('proposal_id')
    explore_subs.add_parser('accept').add_argument('proposal_id')
    reject = explore_subs.add_parser('reject')
    reject.add_argument('proposal_id')
    reject.add_argument('--reason', required=True)
    explore_subs.add_parser('notes').add_argument('hypothesis_id')
    explore_subs.add_parser('resume')
    config = subs.add_parser('config', help='Validate project-local provider settings')
    config_subs = config.add_subparsers(dest='operation', required=True)
    config_check = config_subs.add_parser('check', help='Check settings without revealing credentials')
    config_check.add_argument('--model')
    init = subs.add_parser('init', help='Manually initialize core data (not Framing)')
    init.add_argument('--seed', required=True)
    init.add_argument('--question', required=True)
    hypothesis = subs.add_parser('hypothesis').add_subparsers(dest='operation', required=True)
    add = hypothesis.add_parser('add')
    add.add_argument('--title', required=True)
    add.add_argument('--claim', required=True)
    add.add_argument('--parent', action='append', default=[])
    add.add_argument('--assumption', action='append', default=[])
    add.add_argument('--falsified-if', action='append', default=[])
    action = subs.add_parser('action', help='Checkbox next-actions attached to a hypothesis').add_subparsers(dest='operation', required=True)
    add = action.add_parser('add')
    add.add_argument('target')
    add.add_argument('title')
    action.add_parser('check').add_argument('action_id')
    action.add_parser('uncheck').add_argument('action_id')
    subs.add_parser('actions', help='List actions grouped by hypothesis')
    weekly = subs.add_parser('weekly', help='Seven-day view of how the inquiry changed')
    weekly.add_argument('--days', type=_positive_int, default=7)
    write = subs.add_parser('write', help='Markdown export regenerated from the event log')
    write_subs = write.add_subparsers(dest='operation', required=True)
    write_weekly = write_subs.add_parser('weekly')
    write_weekly.add_argument('--days', type=_positive_int, default=7)
    write_weekly.add_argument('--out', type=Path)
    evidence = subs.add_parser('evidence').add_subparsers(dest='operation', required=True)
    add = evidence.add_parser('add')
    add.add_argument('target')
    _relation(add)
    add.add_argument('--file', required=True, type=Path)
    add.add_argument('--type', choices=sorted(EVIDENCE_TYPES), required=True)
    add.add_argument('--retrieved-at', required=True)
    add.add_argument('--uri')
    link = evidence.add_parser('link')
    link.add_argument('evidence_id')
    link.add_argument('target')
    _relation(link)
    for action in ('start', 'support', 'contest', 'refute', 'suspend', 'continue', 'reopen', 'close'):
        decision = subs.add_parser(action)
        decision.add_argument('target')
        if action != 'start':
            decision.add_argument('--reason', required=True)
        if action in ('support', 'contest', 'refute'):
            decision.add_argument('--evidence', required=True)
        if action == 'reopen':
            decision.add_argument('--condition-evidence', required=True, dest='evidence')
        if action in ('refute', 'close'):
            decision.add_argument('--reopen-if', required=True)
    synthesize = subs.add_parser('synthesize', help='Commit a manually authored synthesis')
    synthesize.add_argument('parents', nargs='+')
    for name in ('title', 'claim', 'reason'):
        synthesize.add_argument('--' + name, required=True)
    show = subs.add_parser('show')
    show.add_argument('target', nargs='?')
    framing = subs.add_parser('framing', help='Saved human-approved framing').add_subparsers(dest='operation', required=True)
    framing.add_parser('start').add_argument('--seed', required=True)
    for action in ('show', 'answer', 'next', 'cancel', 'resume', 'reject', 'accept'):
        command = framing.add_parser(action)
        command.add_argument('session_id')
        if action == 'answer':
            command.add_argument('qid')
            command.add_argument('text')
        if action in ('reject', 'accept'):
            command.add_argument('proposal_id')
        if action == 'reject':
            command.add_argument('--reason', required=True)
        if action == 'cancel':
            command.add_argument('--reason', default='user-cancelled')
        if action == 'next':
            command.add_argument('--regenerate', action='store_true')
            _generation_options(command)
    args = parser.parse_args(argv)
    try:
        if args.command == 'branch':
            from inquiry.features.branch.service import BranchService
            from inquiry.llm.runs import Runner
            service = BranchService(args.dir)
            if args.operation == 'propose':
                factory = ((lambda: (adapter, args.model or 'fake')) if adapter is not None else
                           _openai_factory(args.dir, args.model, args.max_output_tokens, args.timeout,
                                           purpose='branch'))
                result = service.propose(args.parent_id, adapter_factory=factory,
                                         max_output_tokens=args.max_output_tokens or 4000, timeout=args.timeout)
            elif args.operation == 'show':
                result = service.view(args.proposal_id)
            elif args.operation == 'accept':
                result = service.accept(args.proposal_id, args.selected_ids)
            elif args.operation == 'reject':
                result = service.reject(args.proposal_id, args.reason)
            else:
                result = {'recovered': Runner(args.dir).recover()}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.command == 'explore':
            from inquiry.features.operation.service import OperationsService
            from inquiry.llm.runs import Runner
            service = OperationsService(args.dir)
            if args.operation == 'propose':
                factory = ((lambda: (adapter, args.model or 'fake')) if adapter is not None else
                           _openai_factory(args.dir, args.model, args.max_output_tokens, args.timeout,
                                           purpose=args.kind))
                result = service.propose(args.kind, args.target_ids, adapter_factory=factory,
                                         max_output_tokens=args.max_output_tokens or 4000,
                                         timeout=args.timeout)
            elif args.operation == 'show':
                result = service.view(args.proposal_id)
            elif args.operation == 'accept':
                result = {'id': service.accept(args.proposal_id)}
            elif args.operation == 'reject':
                result = service.reject(args.proposal_id, args.reason)
            elif args.operation == 'notes':
                result = service.notes(args.hypothesis_id)
            else:
                result = {'recovered': Runner(args.dir).recover()}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.command == 'chat':
            from inquiry.ui.interactive import run_conversation
            factory = ((lambda: (adapter, args.model or 'fake')) if adapter is not None else
                       _openai_factory(args.dir, args.model, args.max_output_tokens, args.timeout))
            branch_factory = ((lambda: (adapter, args.model or 'fake')) if adapter is not None else
                              _openai_factory(args.dir, args.model, args.max_output_tokens, args.timeout,
                                              purpose='branch'))
            operation_factories = {
                'deepen': ((lambda: (adapter, args.model or 'fake')) if adapter is not None else
                           _openai_factory(args.dir, args.model, args.max_output_tokens, args.timeout,
                                           purpose='deepen')),
                'challenge': ((lambda: (adapter, args.model or 'fake')) if adapter is not None else
                              _openai_factory(args.dir, args.model, args.max_output_tokens, args.timeout,
                                              purpose='challenge')),
                'synthesize': ((lambda: (adapter, args.model or 'fake')) if adapter is not None else
                               _openai_factory(args.dir, args.model, args.max_output_tokens, args.timeout,
                                               purpose='synthesize')),
            }
            run_conversation(args.dir, adapter_factory=factory,
                             branch_factory=branch_factory, operation_factories=operation_factories,
                             max_output_tokens=args.max_output_tokens,
                             timeout=args.timeout)
            return
        if args.command == 'tui':
            from inquiry.ui.tui import run_tui
            ops = ('deepen', 'challenge', 'fork', 'synthesize')
            if adapter is not None:
                op_factories = {op: (lambda a=adapter: (a, args.model or 'fake')) for op in ops}
            else:
                op_factories = {op: _openai_factory(args.dir, args.model, args.max_output_tokens,
                                                    args.timeout, purpose=('branch' if op == 'fork' else op))
                                for op in ops}
            run_tui(args.dir, op_factories=op_factories)
            return
        if args.command == 'config':
            from inquiry.config import check_config
            print(json.dumps(check_config(args.dir, model=args.model), ensure_ascii=False, indent=2))
            return
        commands = Commands(args.dir)
        if args.command == 'framing':
            from inquiry.features.framing.service import FramingService
            service = FramingService(args.dir)
            if args.operation == 'start':
                result = {'session_id': service.start(args.seed)}
            elif args.operation == 'show':
                result = service.view(args.session_id)
            elif args.operation == 'answer':
                result = service.answer(args.session_id, args.qid, args.text)
            elif args.operation == 'next':
                if adapter is not None:
                    result = service.advance(
                        args.session_id, adapter, model=args.model or 'fake',
                        regenerate=args.regenerate,
                        max_output_tokens=args.max_output_tokens, timeout=args.timeout,
                    )
                else:
                    openai_factory = _openai_factory(
                        args.dir, args.model, args.max_output_tokens, args.timeout)
                    result = service.advance(
                        args.session_id, regenerate=args.regenerate,
                        adapter_factory=openai_factory,
                        max_output_tokens=args.max_output_tokens, timeout=args.timeout,
                    )
            elif args.operation == 'cancel':
                result = service.cancel(args.session_id, args.reason)
            elif args.operation == 'resume':
                result = service.resume(args.session_id)
            elif args.operation == 'reject':
                result = service.reject(args.session_id, args.proposal_id, args.reason)
            else:
                result = service.accept(args.session_id, args.proposal_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        elif args.command == 'init':
            result = commands.initialize(args.seed, {'question': args.question})
        elif args.command == 'hypothesis':
            result = commands.add_hypothesis(args.title, args.claim, args.parent, args.assumption, args.falsified_if)
        elif args.command == 'action':
            if args.operation == 'add':
                result = commands.add_action(args.target, args.title)
            else:
                result = commands.check_action(args.action_id, done=args.operation == 'check')
        elif args.command == 'actions':
            state = commands.state()
            if not state.actions:
                print('Actions가 없습니다.')
                return
            for node_id in sorted({action.hypothesis_id for action in state.actions.values()}):
                node = state.hypotheses[node_id]
                print(f'{node.id} {node.title} — {node.status}')
                for action in sorted(state.actions.values(), key=lambda item: item.id):
                    if action.hypothesis_id == node_id:
                        print(f"  [{'x' if action.done else ' '}] {action.id} {action.title}")
            return
        elif args.command in ('weekly', 'write'):
            from inquiry.domain.replay import replay
            from inquiry.store.store import Store
            from inquiry.weekly import build, render_markdown, render_text
            events = Store(args.dir).read_all()
            report = build(events, replay(events), days=args.days)
            if args.command == 'weekly':
                print(render_text(report))
            elif args.out is not None:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(render_markdown(report), encoding='utf-8')
                print(json.dumps({'out': str(args.out)}, ensure_ascii=False))
            else:
                print(render_markdown(report))
            return
        elif args.command == 'evidence':
            relation = 'supports' if args.supports else 'challenges'
            if args.operation == 'add':
                result = commands.add_evidence(args.target, relation, args.type,
                    args.file.read_text(encoding='utf-8'), args.retrieved_at, args.uri)
            else:
                result = commands.link_evidence(args.evidence_id, args.target, relation)
        elif args.command == 'synthesize':
            result = commands.synthesize(args.parents, args.title, args.claim, args.reason)
        elif args.command == 'show':
            state = commands.state()
            if args.target:
                obj = state.hypotheses.get(args.target) or state.evidence.get(args.target)
                if obj is None:
                    raise ValueError('Object not found.')
                print(json.dumps(asdict(obj), ensure_ascii=False, indent=2))
            else:
                print(json.dumps(asdict(state), ensure_ascii=False, indent=2))
            return
        else:
            result = commands.decide(args.target, args.command, reason=getattr(args, 'reason', ''),
                                     evidence_id=getattr(args, 'evidence', None), reopen_if=getattr(args, 'reopen_if', None))
    except ImportError:
        parser.error(_OPTIONAL_DEPENDENCIES)
    except (ValueError, StoreError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({'id': result}, ensure_ascii=False))

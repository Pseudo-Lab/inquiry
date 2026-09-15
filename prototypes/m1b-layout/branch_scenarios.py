#!/usr/bin/env python3
"""Hand-routed branch scenarios for visual review, not a graph/state engine."""
import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from presentation import PALETTE, colorize, STATES, cells, fit


@dataclass(frozen=True)
class Node:
    id: str
    title: str
    state: str
    parents: tuple


SCENARIOS = {
    'continue': {
        'title': '01 / Continue & fork', 'focus': 'H-012',
        'nodes': [
            Node('ROOT', '같은 실수를 반복하지 않기', 'exploring', ()),
            Node('H-001', '다음 세션에도 지침 전달', 'exploring', ('ROOT',)),
            Node('H-003', 'handover로 지침 넘기기', 'supported', ('H-001',)),
            Node('H-007', '작업 전에 관련 규칙 읽기', 'exploring', ('H-003',)),
            Node('H-011', '모든 규칙을 읽으면 방해될까?', 'contested', ('H-007',)),
            Node('H-012', '현재 작업에 맞는 규칙만 읽기', 'exploring', ('H-007',)),
            Node('H-002', '바로 쓸 수 있는 규칙 만들기', 'suggested', ('H-001',)),
        ],
        'rows': [
            ('*', 'ROOT'), ('│', ''), ('*', 'H-001'), ('│╲', 'Fork / Support'),
            ('│ *', 'H-003'), ('│ │', ''), ('│ *', 'H-007'),
            ('│ │╲', 'Fork again / Challenge'), ('│ │ *', 'H-011'), ('│ │ │', ''),
            ('│ * │', 'H-012'), ('│ │ │', '> Selected · H-007에서 이어서 탐색'),
            ('│ │ │', ''), ('* │ │', 'H-002'), ('│ │ │', ''),
            ('┆ ┆ ┆', 'Open branches / 아직 탐색 중'),
        ],
        'detail': [
            'Main: ROOT → H-001 → H-002',
            'Support: H-001 → H-003 → H-007 → H-012',
            'Challenge: H-007 → H-011',
        ],
    },
    'merge': {
        'title': '02 / Merge & continue', 'focus': 'SYN-01',
        'nodes': [
            Node('ROOT', '같은 실수를 반복하지 않기', 'exploring', ()),
            Node('H-001', '다음 세션에도 지침 전달', 'supported', ('ROOT',)),
            Node('H-003', 'handover로 지침 넘기기', 'supported', ('H-001',)),
            Node('H-002', '재사용할 규칙으로 정리', 'synthesized', ('H-001',)),
            Node('H-007', '관련 규칙을 자동으로 찾기', 'synthesized', ('H-003',)),
            Node('SYN-01', '규칙 저장과 자동 참조를 결합', 'exploring', ('H-002', 'H-007')),
            Node('H-008', '새 세션에서 재발 여부 확인', 'exploring', ('SYN-01',)),
        ],
        'rows': [
            ('*', 'ROOT'), ('│', ''), ('*', 'H-001'), ('│╲', 'Fork / Support'),
            ('│ *', 'H-003'), ('│ │', ''), ('* │', 'H-002'),
            ('│ │', 'Into SYN-01 / 원래 가설은 이력으로 유지'), ('│ *', 'H-007'),
            ('│ │', 'Into SYN-01 / 원래 가설은 이력으로 유지'),
            ('│╱', 'Merge / H-002 + H-007'), ('◆', 'SYN-01'),
            ('│', '> Selected · 두 부모를 가진 새 통합 가설'), ('│', ''),
            ('*', 'H-008'), ('┆', 'Continue / 통합 뒤에도 탐색 계속'),
        ],
        'detail': [
            'Inputs: H-002 + H-007 · Synthesized',
            'New hypothesis: SYN-01 · Exploring',
            'Next: SYN-01 → H-008',
        ],
    },
    'endings': {
        'title': '03 / Refuted & closed', 'focus': 'H-007',
        'nodes': [
            Node('ROOT', '같은 실수를 반복하지 않기', 'exploring', ()),
            Node('H-001', '다음 세션에도 지침 전달', 'exploring', ('ROOT',)),
            Node('H-003', '실패 기록을 자동으로 읽기', 'exploring', ('H-001',)),
            Node('H-007', '기록을 읽으면 항상 해결된다', 'refuted', ('H-003',)),
            Node('H-005', '모든 작업 도구를 교체하기', 'human-closed', ('H-001',)),
            Node('H-002', '필요한 규칙만 전달하는 방법', 'exploring', ('H-001',)),
        ],
        'rows': [
            ('*', 'ROOT'), ('│', ''), ('*', 'H-001'), ('│╲', 'Fork / Support'),
            ('│ *', 'H-003'), ('│ │', ''), ('│ ×', 'H-007'),
            ('│', '> Selected · 반례를 확인해 이 가지의 탐색 중단'),
            ('│', 'Reason: 지침을 읽었는데도 같은 실수가 발생'),
            ('│', 'Evidence: 재실행 사례 03 (가짜 데이터)'),
            ('│', 'Reopen: 적용 조건을 수정하면 다시 검토'), ('│', ''),
            ('│╲', 'Fork / Alternative'), ('│ ⊘', 'H-005'),
            ('│', 'Reason: 이번 탐구 범위를 벗어나 사람이 종료'),
            ('│', 'Evidence: 범위 검토 메모 (가짜 데이터)'),
            ('│', 'Reopen: 도구 교체가 필요해지면 다시 검토'), ('│', ''),
            ('*', 'H-002'), ('┆', 'Main path continues / 주계보는 계속'),
        ],
        'detail': [
            '× Refuted: 반박 근거로 중단 · 자동 재개하지 않음',
            '⊘ Closed by user: 사람의 결정 · 거짓이라는 뜻은 아님',
            '종료 이유와 근거는 지우지 않고 남김',
        ],
    },
}


def render(name, width=100, color=False):
    if name not in SCENARIOS or width not in (80, 100, 120):
        raise ValueError('Choose continue/merge/endings and width 80/100/120.')
    scenario = SCENARIOS[name]
    nodes = {node.id: node for node in scenario['nodes']}
    result = []
    widths = (5, 7, width - 41, 16)

    def ansi(rgb, background=False):
        return '\x1b[' + ('48' if background else '38') + ';2;' + ';'.join(map(str, rgb)) + 'm'

    base = ansi(PALETTE['background'], True)
    selection = ansi(PALETTE['selection'], True)
    border_color = ansi(PALETTE['border'])

    def wide(text):
        plain = '│ ' + fit(text, width - 4) + ' │'
        result.append(colorize(plain).rstrip('\n') if color else plain)

    def rule(left, middle, right):
        plain = left + middle.join('─' * (w + 2) for w in widths) + right
        result.append(colorize(plain).rstrip('\n') if color else plain)

    def table(graph, identity='', title='', state='', selected=False):
        values = [fit(value, w) for value, w in zip((graph, identity, title, state), widths)]
        if not color:
            result.append('│ ' + ' │ '.join(values) + ' │')
            return
        background = selection if selected else base
        prefix = base + border_color + '│' + background + ' '
        for i, char in enumerate(values[0]):
            role = 'selected' if i == 0 else 'support' if i <= 2 else 'challenge'
            if char not in '*│┆╲╱◆×⊘':
                role = 'muted'
            if char == '╲' and title.startswith('Fork / Alternative'):
                role = 'challenge'
            if char in ('╱', '◆'):
                role = 'purple'
            elif char in ('×', '⊘'):
                role = 'challenge' if char == '×' else 'muted'
            prefix += ansi(PALETTE[role]) + char
        body = ' │ ' + ' │ '.join(values[1:]) + ' '
        decorated = colorize(body).rstrip('\n').replace(selection, background).replace(base, background)
        result.append(prefix + decorated + base + border_color + '│\x1b[0m')

    def note(text, graph=''):
        # Explanations use exactly the same title column as hypotheses.
        parts, current = [], ''
        for word in text.split():
            if current and cells(current + ' ' + word) > widths[2]:
                parts.append(current)
                current = ''
            current = (current + ' ' + word).strip()
        parts.append(current)
        for part in parts:
            table(graph, title=part)

    top = '╭' + '─' * (width - 2) + '╮'
    bottom = '╰' + '─' * (width - 2) + '╯'
    result.append(colorize(top).rstrip('\n') if color else top)
    wide('inquiry / Branch log · ' + scenario['title'])
    wide('세션이 바뀌어도 같은 실수를 막으려면?')
    wide(f'Static preview · Sample data · {len(nodes)} nodes · Focus {scenario["focus"]}')
    rule('├', '┬', '┤')
    table('GRAPH', 'ID', 'HYPOTHESIS', 'STATUS')
    rule('├', '┼', '┤')
    for graph, text in scenario['rows']:
        if text in nodes:
            node = nodes[text]
            symbol, status = STATES[node.state]
            if node.state == 'human-closed':
                status = 'Closed by user'
            table(graph, node.id, node.title, f'{symbol} {status}', node.id == scenario['focus'])
        else:
            note(text, graph)
    rule('├', '┴', '┤')
    wide('Details')
    for line in scenario['detail']:
        wide(line)
    wide('')
    wide('Preview only · No state changes · Top to bottom = ancestry')
    result.append(colorize(bottom).rstrip('\n') if color else bottom)
    return '\n'.join(result) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=SCENARIOS, default='continue')
    parser.add_argument('--width', type=int, choices=(80, 100, 120), default=100)
    parser.add_argument('--color', choices=('auto', 'always', 'never'), default='auto')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        for name in SCENARIOS:
            for width in (80, 100, 120):
                for color, extension in ((False, 'txt'), (True, 'ansi')):
                    (args.out / f'{name}-{width}.{extension}').write_text(render(name, width, color), encoding='utf-8')
        print(f'9 plain + 9 color snapshots: {args.out}')
    else:
        color = args.color == 'always' or (args.color == 'auto' and sys.stdout.isatty() and 'NO_COLOR' not in os.environ)
        print(render(args.scenario, args.width, color), end='')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Scale study: connected fixture groups paginated without discarding graph data."""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys

from branch_scenarios import Node, SCENARIOS, render as render_scenario


SMALL = {
    'focus': 'H-001',
    'nodes': [Node('ROOT', '같은 실수를 반복하지 않기', 'exploring', ()),
              Node('H-001', '다음 세션에도 지침 전달', 'exploring', ('ROOT',)),
              Node('H-002', 'handover에 조건 기록', 'supported', ('H-001',)),
              Node('H-003', '실제 작업에서 다시 확인', 'exploring', ('H-001',))],
    'rows': [('*', 'ROOT'), ('│', ''), ('*', 'H-001'), ('│╲', 'Fork / Support'),
             ('│ *', 'H-002'), ('│', ''), ('*', 'H-003'), ('┆', 'Continue')],
    'detail': ['Main: ROOT → H-001 → H-003', 'Support: H-001 → H-002'],
}


@dataclass(frozen=True)
class Dataset:
    nodes: tuple
    groups: tuple


@dataclass(frozen=True)
class View:
    text: str
    visible: tuple
    hidden: int
    context: str
    page: int
    pages: int
    density: str


def make_dataset(count):
    if count not in (10, 30, 100):
        raise ValueError('Node count must be 10, 30, or 100.')
    templates = {**SCENARIOS, 'fork': SMALL}
    sizes = {name: len(value['nodes']) - 1 for name, value in templates.items()}
    reachable = {0}
    for n in range(1, count):
        if any(n - size in reachable for size in sizes.values()):
            reachable.add(n)
    nodes = [Node('ROOT', '같은 실수를 반복하지 않기', 'exploring', ())]
    groups = []
    cycle = ('merge', 'continue', 'endings')
    remaining = count - 1
    while remaining:
        preferred = cycle[len(groups) % len(cycle)]
        kind = next(name for name in (preferred, 'merge', 'continue', 'endings', 'fork')
                    if remaining - sizes[name] in reachable)
        template = templates[kind]
        context = nodes[-1]
        mapping = {'ROOT': context.id}
        for original in template['nodes'][1:]:
            mapping[original.id] = ('SYN-' if original.id.startswith('SYN-') else 'H-') + f'{len(nodes) + len(mapping) - 1:03d}'
        local = [context]
        for original in template['nodes'][1:]:
            state = 'exploring' if original is template['nodes'][-1] else original.state
            local.append(Node(mapping[original.id], original.title, state,
                              tuple(mapping[parent] for parent in original.parents)))
        pattern = re.compile('|'.join(re.escape(key) for key in sorted(mapping, key=len, reverse=True)))

        def replace(text):
            return pattern.sub(lambda match: mapping[match.group()], text)

        groups.append(dict(nodes=local, kind=kind, focus=mapping[template['focus']],
                           rows=[(graph, replace(text)) for graph, text in template['rows']],
                           detail=[replace(line) for line in template['detail']]))
        nodes.extend(local[1:])
        remaining -= len(local) - 1
    return Dataset(tuple(nodes), tuple(groups))


def render(width=120, count=30, page=1, color=False):
    if width not in (80, 120, 160):
        raise ValueError('Width must be 80, 120, or 160.')
    dataset = make_dataset(count)
    if not 1 <= page <= len(dataset.groups):
        raise ValueError(f'Page must be between 1 and {len(dataset.groups)}.')
    source = dataset.groups[page - 1]
    visible = tuple(node.id for node in source['nodes'])
    hidden = count - len(visible)
    compact = count == 100 or (width == 80 and count >= 30)
    scenario = dict(source)
    scenario['title'] = f'{count} nodes / {"compact" if compact else "normal"} / Group {page}'
    scenario['summary'] = f'Static preview · {len(visible)}/{count} shown · {hidden} hidden · Page {page}/{len(dataset.groups)}'
    scenario['footer'] = f'Context {visible[0]} repeated · --page 1..{len(dataset.groups)} · Sample data only'
    if compact:
        # Never hide nodes or termination metadata; only blank spacer rows are removed.
        scenario['rows'] = [(graph, text) for graph, text in source['rows'] if text]
    text = render_scenario('', width, color, scenario=scenario, height=40)
    return View(text, visible, hidden, visible[0], page, len(dataset.groups), 'compact' if compact else 'normal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=int, choices=(80, 120, 160), default=120)
    parser.add_argument('--nodes', type=int, choices=(10, 30, 100), default=30)
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--color', choices=('auto', 'always', 'never'), default='auto')
    parser.add_argument('--matrix', type=Path, help='Generate all 9 combinations and every page')
    args = parser.parse_args()
    try:
        if args.matrix:
            args.matrix.mkdir(parents=True, exist_ok=True)
            summary = []
            for width in (80, 120, 160):
                for count in (10, 30, 100):
                    dataset = make_dataset(count)
                    records = []
                    for page in range(1, len(dataset.groups) + 1):
                        view = render(width, count, page)
                        stem = f'map-{width}-{count}-p{page:02d}'
                        (args.matrix / f'{stem}.txt').write_text(view.text, encoding='utf-8')
                        (args.matrix / f'{stem}.ansi').write_text(render(width, count, page, True).text, encoding='utf-8')
                        records.append(dict(page=page, visible=list(view.visible), context=view.context,
                                            hidden=view.hidden, kind=dataset.groups[page-1]['kind']))
                    summary.append(dict(width=width, nodes=count, pages=len(records), height=40,
                                        density=view.density, records=records))
            (args.matrix / 'manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'9 combinations / {sum(item["pages"] for item in summary)} pages: {args.matrix}')
        else:
            color = args.color == 'always' or (args.color == 'auto' and sys.stdout.isatty() and 'NO_COLOR' not in os.environ)
            print(render(args.width, args.nodes, args.page, color).text, end='')
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()

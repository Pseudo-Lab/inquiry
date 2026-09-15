"""Presentation helpers for the selected Git-log prototype."""
import re
import unicodedata

STATES = {
    'suggested': ('◌', 'Suggested'),
    'exploring': ('◉', 'Exploring'),
    'supported': ('●', 'Supported'),
    'contested': ('◐', 'Contested'),
    'suspended': ('∙', 'Suspended'),
    'refuted': ('×', 'Refuted'),
    'synthesized': ('◆', 'Synthesized'),
    'human-closed': ('⊘', 'Closed'),
}


def cells(text: str) -> int:
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1
               for c in text)


def fit(text: str, width: int) -> str:
    """Pad/clip in terminal cells, preserving Korean and combining characters."""
    if cells(text) <= width:
        return text + ' ' * (width - cells(text))
    result = ''
    for char in text:
        if cells(result + char) > width - 1:
            break
        result += char
    return result + '…' + ' ' * (width - 1 - cells(result))

PALETTE = {
    'text': (226, 232, 240), 'muted': (155, 170, 189), 'border': (77, 95, 117),
    'selected': (125, 211, 252), 'support': (134, 239, 172), 'challenge': (253, 186, 116),
    'purple': (196, 181, 253), 'background': (12, 18, 28), 'selection': (25, 47, 67),
}


def colorize(text):
    """Decorate completed lines so ANSI never participates in cell-width calculations."""
    result = []
    plain_lines = text.splitlines()
    for index, line in enumerate(plain_lines):
        stripped = line.strip()
        muted = stripped.startswith(('Static preview', 'View scope:', 'From ROOT', 'ROOT:', 'H-002:', 'ID '))
        colors = [PALETTE['muted' if muted else 'text']] * len(line)
        selected = '> Selected' in line or '[ H-001' in line
        bg = PALETTE['selection' if selected else 'background']

        def mark(pattern, role):
            for match in re.finditer(pattern, line):
                colors[match.start():match.end()] = [PALETTE[role]] * (match.end() - match.start())

        mark(r'[─│╭╮╰╯├└]+', 'border')
        mark(r'\bSupport\b|\bSupported\b|\+', 'support')
        mark(r'\bChallenge\b|\bContested\b|\bRefuted\b', 'challenge')
        mark(r'\bSuggested\b|\bSuspended\b|\bClosed\b', 'muted')
        mark(r'\bSynthesized\b', 'purple')
        mark(r'H-001|> Selected|Exploring|Main path|Selected /|Hypotheses|Next /|Branch log', 'selected')
        if re.match(r'^\s*[│*]', line) and '│' not in line[8:]:
            mark(r'^\s*[│*]', 'selected')
            branch_line = plain_lines[index + 1] if '╲' in line and index + 1 < len(plain_lines) else line
            role = 'support' if re.search(r'\bSupport\b', branch_line) else 'challenge' if re.search(r'\bChallenge\b', branch_line) else 'selected'
            mark(r'╲|\*', role)
        if stripped == '다음 세션에도 지침 전달':
            colors = [PALETTE['selected']] * len(line)
        value = '\x1b[48;2;' + ';'.join(map(str, bg)) + 'm'
        previous = None
        for char, rgb in zip(line, colors):
            if rgb != previous:
                value += '\x1b[38;2;' + ';'.join(map(str, rgb)) + 'm'
                previous = rgb
            value += char
        result.append(value + '\x1b[0m')
    return '\n'.join(result) + '\n'

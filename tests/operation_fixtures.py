"""Fresh synthetic model outputs for operation tests."""


def deepen_output():
    return {
        'assumptions': ['시작 시 기록을 읽는다'],
        'falsified_if': ['기록을 읽어도 동일 오류가 반복된다'],
        'reason': '전달과 실행을 구분해 확인한다',
    }


def challenge_output():
    return {'objections': [{
        'claim': '긴 기록은 핵심 지침을 가릴 수 있다',
        'reason': '문맥 양이 늘면 우선순위가 불명확해진다',
        'check': '짧은 기록과 긴 기록의 오류 재발을 비교한다',
    }]}


def synthesis_output():
    return {
        'title': '짧은 기록과 실행 검증',
        'claim': '핵심 기록과 회귀 검증을 함께 사용한다',
        'assumptions': ['검증 가능한 실패 사례가 있다'],
        'falsified_if': ['두 방법을 함께 써도 재발이 줄지 않는다'],
        'reason': '문맥 전달과 실행 확인을 결합한다',
        'unresolved': ['검증하기 어려운 판단 오류는 남는다'],
    }


def supported_pair(root):
    """Create two real, independently supported synthesis parents."""
    from inquiry.commands import Commands

    commands = Commands(root)
    commands.initialize('seed', {'question': 'question'})
    parents = []
    for label in ('기록 전달', '실행 검증'):
        hypothesis_id = commands.add_hypothesis(label, label + '은 반복 실패를 줄일 수 있다')
        commands.decide(hypothesis_id, 'start')
        evidence_id = commands.add_evidence(
            hypothesis_id, 'supports', 'human-judgment',
            '오프라인 테스트용 판단이며 실제 검증 자료가 아니다', '2026-09-21T00:00:00Z')
        commands.decide(hypothesis_id, 'support', reason='합성 테스트 상태 준비',
                        evidence_id=evidence_id)
        parents.append(hypothesis_id)
    return tuple(parents)

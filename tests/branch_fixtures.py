"""Hand-authored proposals, not live model-quality evidence."""


def branch_output():
    return {'candidates': [
        {'candidate_id': 'C-1', 'title': '실패 기록 전달',
         'claim': '실패 기록을 다음 세션 시작 시 읽으면 반복 실수를 줄일 수 있다',
         'difference': '세션 시작 시 문맥 전달'},
        {'candidate_id': 'C-2', 'title': '검증 절차 자동화',
         'claim': '반복 실수를 회귀 테스트로 만들면 재발을 감지할 수 있다',
         'difference': '기록보다 실행 결과 검증'},
        {'candidate_id': 'C-3', 'title': '작업 범위 축소',
         'claim': '한 번에 맡기는 작업 범위를 줄이면 지침 누락이 줄어들 수 있다',
         'difference': '입력 정보의 양 조절'},
    ]}

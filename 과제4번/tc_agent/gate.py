"""생성 → 검사 → (문제 있으면) 지적 사항을 붙여 다시 생성. 이 프로토타입에서 되풀이되는 유일한 루프다.

트리 만들기, AC 뽑기, TC 쓰기가 모두 같은 모양이라 여기 한 곳에 둔다. 무엇을 만들고 무엇을 검사하는지는 호출한 쪽이 정한다.

    result = run_gate(first_draft, check=..., revise=...)
    result.output      마지막 결과물
    result.passed      큰 문제(major)가 없으면 True
    result.issues      마지막 검사에서 나온 문제 전부 (minor 포함, 비고로 남길 것)
    result.revisions   다시 만든 횟수

큰 문제가 남아 있어도 한도(MAX_REVISIONS)를 넘으면 멈춘다. 버리거나 통과시키지 않고 passed=False 로 돌려주면,
호출한 쪽이 FAIL 로 표시하거나 잘라낸다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .models import Issue

T = TypeVar("T")

MAX_REVISIONS = 2          # 트리·AC·TC 공통. 근거 없이 정한 값이라 EVALUATION.md 의 재작성 결과(3.6)로 재볼 것


@dataclass
class GateResult(Generic[T]):
    output: T
    issues: list[Issue]
    passed: bool
    revisions: int

    @property
    def major(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "major"]


def run_gate(first: T, check: Callable[[T], list[Issue]], revise: Callable[[T, list[Issue]], T],
             max_revisions: int | None = None) -> GateResult[T]:
    """check 는 문제 목록을, revise 는 (이전 결과, 큰 문제 목록)을 받아 새 결과를 돌려준다."""
    limit = MAX_REVISIONS if max_revisions is None else max_revisions
    output, revisions = first, 0
    while True:
        issues = check(output)
        major = [i for i in issues if i.severity == "major"]
        if not major:
            return GateResult(output, issues, True, revisions)
        if revisions >= limit:
            return GateResult(output, issues, False, revisions)
        output = revise(output, major)
        revisions += 1

"""파이프라인이 주고받는 데이터 모양.

기획서 -> 기능분류트리(FeatureNode) -> leaf별 요구사항(Requirement) -> 테스트케이스(TestCase) 순으로 내려간다.
TC 의 대/중/소분류는 따로 붙이지 않고 leaf의 트리 경로를 그대로 가져온다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

PRIORITIES = ("P0", "P1", "P2")
SCENARIOS = ("정상", "경계", "예외", "실패", "권한", "상태 변화", "동시성")


@dataclass
class FeatureNode:
    """기능분류트리의 노드. 루트는 기능 전체 이름이고, 대/중/소분류는 그 아래 1~3단계다."""
    name: str
    quote: str = ""                       # 이 기능이 나온 기획서 문장 (원문 그대로)
    children: list["FeatureNode"] = field(default_factory=list)
    id: str = ""                          # F1, F1.2 처럼 코드가 붙인다. 모델이 준 id 는 안 쓴다
    # 마크다운으로 트리를 직접 넣을 때만 채워진다
    acs: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    priority: str = ""

    @property
    def is_leaf(self) -> bool:
        return not self.children


@dataclass
class Requirement:
    """leaf 하나에서 뽑은 요구사항. AC(인수조건)가 TC 를 만드는 1차 근거다."""
    id: str                               # leaf id
    path: list[str]                       # 대분류 -> 중분류 -> 소분류
    title: str
    acs: list[str]                        # 모든 AC 는 TC 가 최소 하나씩 다뤄야 한다
    hints: list[str] = field(default_factory=list)
    priority: str = "P1"

    @property
    def source_text(self) -> str:
        """TC 의 수치를 대조할 때 기준으로 삼는 텍스트."""
        return "\n".join([self.title, *self.acs, *self.hints])


@dataclass
class Gap:
    """기능은 있는데 기획서에 동작이 안 적힌 leaf. TC 를 만들지 않고 기획 확인 요청으로 올린다."""
    id: str
    path: list[str]
    reason: str


@dataclass
class Outline:
    """계획 단계 결과. 스텝과 기대결과는 작성 단계에서 채운다."""
    subject: str
    scenario: str
    priority: str
    covers: list[int]                     # 이 TC 가 다루는 AC 번호(0부터)


@dataclass
class TestCase:
    no: int
    ri: str                               # leaf id
    path: list[str]                       # 대/중/소분류
    subject: str
    scenario: str
    priority: str
    precondition: str
    steps: list[str]
    expected: list[str]
    covers: list[int] = field(default_factory=list)
    status: str = "PENDING"               # PASS | FAIL
    revisions: int = 0                    # 다시 쓴 횟수
    notes: list[str] = field(default_factory=list)   # 끝내 못 고친 문제 (사람이 볼 비고)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Issue:
    """검증에서 찾은 문제 하나."""
    rule: str
    severity: str                         # major: 고쳐야 함 / minor: 비고만
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}/{self.rule}] {self.message}"


@dataclass
class PipelineResult:
    tree: FeatureNode
    test_cases: list[TestCase]
    gaps: list[Gap]                       # 기획 확인이 필요한 leaf
    excluded: list[dict]                  # 계획 단계에서 일부러 뺀 시나리오와 이유
    uncovered_acs: dict[str, list[int]]   # leaf id -> 어떤 TC 도 안 다룬 AC 번호
    tree_issues: list[str]                # 트리 검증에서 끝내 못 고친 문제
    pruned: list[str]                     # 원문 근거가 없어 잘라낸 노드
    stats: dict
    trace: list = field(default_factory=list)   # trace.Event 목록 — 어느 단계에서 무엇을 했는지
    requirements: list = field(default_factory=list)   # Requirement 목록 — 평가할 때 AC 수를 세려고 결과에 남긴다

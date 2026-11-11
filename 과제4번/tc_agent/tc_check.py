"""④ TC 검사: 만든 TC 가 쓸 만한지 본다. 이 프로젝트에서 가장 힘을 준 부분이다.

LLM 이 만든 TC 는 그럴듯하지만 틀린 경우가 많아서 두 번 거른다.

  1) 규칙 검사: 형식 위반, 금지 표현, 분량 초과, 원문에 없는 수치. 공짜고 결과가 늘 같다.
  2) LLM Judge: 정확성/완결성/명확성처럼 의미를 봐야 하는 것만 맡긴다. (prompts/judge.md)

규칙으로 잡을 수 있는 건 Judge 에게 안 맡긴다. 규칙에서 큰 문제(major)가 나오면 어차피 다시 쓰니까 Judge 는 부르지도 않는다.
TC 하나씩 검사하고, 마지막에 어떤 TC 도 다루지 않은 AC 가 있는지 한 번 더 본다(uncovered_acs).
"""
from __future__ import annotations

import json
import re

from . import prompts
from .llm import LLMClient, parse_json
from .models import Issue, Requirement, TestCase

MAX_STEPS = 5
MAX_EXPECTED = 3
MAX_SUBJECT_LEN = 30

_STYLE = [
    (re.compile(r"\d+(?:\.\d+)?\s*(?:px|pt|rem|em)\b", re.I), "픽셀/단위 스타일 값"),
    (re.compile(r"#[0-9a-fA-F]{6}\b"), "컬러 코드"),
    (re.compile(r"node-?id", re.I), "디자인 툴 식별자"),
]
_LOOP = re.compile(r"반복|각각|모두 확인")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ENUM_PREFIX = re.compile(r"^\s*\d+[.)]\s*")      # "1. " 같은 번호는 수치로 안 본다


def numbers_of(text: str) -> set[str]:
    """텍스트에 든 수치 집합 (천 단위 쉼표는 뗀다). AC 도출과 TC 검사가 같은 기준을 쓰도록 공개해 둔다."""
    return {n.replace(",", "") for n in _NUM.findall(text)}


def check_rules(tc: TestCase, req: Requirement) -> list[Issue]:
    issues: list[Issue] = []

    def major(rule: str, msg: str):
        issues.append(Issue(rule, "major", msg))

    if not tc.steps:
        major("empty_steps", "테스트스텝이 비어 있음")
    if not tc.expected:
        major("empty_expected", "기대결과가 비어 있음")
    if len(tc.steps) > MAX_STEPS:
        major("steps_too_long", f"스텝 {len(tc.steps)}줄 — {MAX_STEPS}줄 이하로 줄이고 확인할 것 하나만 남길 것")
    if len(tc.expected) > MAX_EXPECTED:
        major("expected_too_long", f"기대결과 {len(tc.expected)}줄 — {MAX_EXPECTED}줄 이하로")
    if len(tc.subject) > MAX_SUBJECT_LEN:
        major("subject_too_long", f"서브젝트 {len(tc.subject)}자 — {MAX_SUBJECT_LEN}자 이내로")

    body = "\n".join([tc.precondition, *tc.steps, *tc.expected])
    for pat, label in _STYLE:
        m = pat.search(body)
        if m:
            major("style_value", f"{label} '{m.group()}' 는 TC 에 쓰지 말 것")
    if _LOOP.search("\n".join(tc.steps)):
        major("loop_words", "반복·순회 표현 금지 — 값마다 TC 를 나눌 것")

    # 환각 탐지: 기대결과에 나온 수치는 원문에 있어야 한다.
    # 스텝의 입력값은 수행하는 사람이 정하는 거라 대조하지 않는다.
    allowed = numbers_of(req.source_text)
    for line in tc.expected:
        for n in numbers_of(_ENUM_PREFIX.sub("", line)):
            if n not in allowed:
                major("ungrounded_number", f"기대결과의 수치 '{n}' 가 원문(AC·힌트)에 없음 — 지어낸 값이면 삭제할 것")
    return issues


def judge(tc: TestCase, req: Requirement, llm: LLMClient) -> list[Issue]:
    payload = {
        "source": {"title": req.title, "acs": req.acs, "hints": req.hints},
        "test_case": {"subject": tc.subject, "scenario": tc.scenario, "precondition": tc.precondition,
                      "steps": tc.steps, "expected": tc.expected},
    }
    try:
        data = parse_json(llm.complete(prompts.JUDGE_SYSTEM, json.dumps(payload, ensure_ascii=False)))
    except ValueError as e:
        # Judge 응답이 깨졌다고 TC 를 통과시키지도 버리지도 않는다. 비고에만 남겨 사람이 보게 한다.
        return [Issue("judge_error", "minor", f"Judge 응답 파싱 실패: {e}")]
    issues = []
    for dim in ("correctness", "completeness", "clarity"):
        d = data.get(dim) or {}
        if str(d.get("verdict", "")).upper() == "FAIL":
            issues.append(Issue(dim, "major", d.get("reason") or f"{dim} 기준 미달"))
    return issues


def check_tc(tc: TestCase, req: Requirement, llm: LLMClient | None = None) -> list[Issue]:
    """규칙 검사를 먼저 하고, 큰 문제가 없을 때만 Judge 를 부른다. llm 이 없으면 규칙만 본다."""
    issues = check_rules(tc, req)
    if not any(i.severity == "major" for i in issues) and llm is not None:
        issues += judge(tc, req, llm)
    return issues


def uncovered_acs(requirements: list[Requirement], test_cases: list[TestCase]) -> dict[str, list[int]]:
    """leaf id -> 어떤 TC 도 다루지 않은 AC 번호(0부터). 계획이 놓친 AC 는 사람이 보게 리포트에 올린다."""
    covered: dict[str, set[int]] = {}
    for tc in test_cases:
        covered.setdefault(tc.ri, set()).update(tc.covers)
    out: dict[str, list[int]] = {}
    for req in requirements:
        missing = [i for i in range(len(req.acs)) if i not in covered.get(req.id, set())]
        if missing:
            out[req.id] = missing
    return out

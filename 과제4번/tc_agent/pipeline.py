"""전체 흐름. 네 단계이고, 생성과 검사가 짝으로 돈다.

    기획서
      ↓
    ① 트리 생성  ⇄  ② 트리 검사        문제 있으면 지적 사항을 붙여 ①을 다시 (gate.MAX_REVISIONS 회까지)
      ↓ 통과
    ③ TC 생성    ⇄  ④ TC 검사          문제 있는 TC 한 건만 ③을 다시 (gate.MAX_REVISIONS 회까지, 못 고치면 FAIL)
      ↓
    리포트

  stage_tree  ①②  tree.derive_tree  ⇄ tree_check.check_tree
  stage_tc    ③④  tc.derive_requirements -> tc.plan -> tc.write  ⇄ tc_check.check_tc

"생성 → 검사 → 재생성" 루프는 gate.run_gate 한 곳에만 있다. 이 파일은 무엇을 만들고 무엇으로 검사할지만 잇는다.
각 단계는 trace 에 한 줄씩 남긴다(trace.py). 리포트의 "실행 흐름"이 이걸 보여 준다.
"""
from __future__ import annotations

import logging
from typing import Callable

from .gate import run_gate
from .llm import LLMClient
from .models import FeatureNode, Gap, Outline, PipelineResult, Requirement, TestCase
from .tc import derive_requirements, plan, write
from .tc_check import check_tc, uncovered_acs
from .trace import WARN, Event, Trace
from .tree import assign_ids, derive_tree, leaves
from .tree_check import check_tree, prune_ungrounded

log = logging.getLogger("tc_agent")


# ①② 트리 생성 ⇄ 트리 검사

def stage_tree(spec_text: str, llm: LLMClient, tree: FeatureNode | None,
               trace: Trace) -> tuple[FeatureNode, list[str], list[str]]:
    """(트리, 남은 트리 문제, 잘라낸 노드). tree 를 직접 받았으면 생성도 검사도 건너뛴다."""
    if tree is not None:
        trace.add("tree_build", f"트리를 직접 입력받음 — 생성·검사 생략 (leaf {len(leaves(tree))}개)")
        return tree, [], []

    first = derive_tree(spec_text, llm)
    trace.add("tree_build", f"생성 — leaf {len(leaves(first))}개")
    redone = [0]

    def check(t: FeatureNode):
        issues = check_tree(t, spec_text, llm)
        major = [i for i in issues if i.severity == "major"]
        trace.add("tree_check", "통과 (지어냄·누락·모양)" if not major
                  else f"문제 {len(major)}건: " + "; ".join(str(i) for i in major))
        return issues

    def revise(t: FeatureNode, major):
        redone[0] += 1
        trace.add("tree_build", f"지적 사항을 붙여 {redone[0]}회차 재생성")
        return derive_tree(spec_text, llm, previous=t, feedback=[str(i) for i in major])

    res = run_gate(first, check, revise)
    tree = res.output
    if not res.passed:
        trace.add("tree_check", f"문제 {len(res.major)}건이 재생성 {res.revisions}회 후에도 남음", WARN)
    pruned = prune_ungrounded(tree, spec_text)       # 지어낸 노드만 잘라낸다. 누락은 코드로 못 고친다
    if pruned:
        trace.add("tree_check", f"원문 근거 없는 노드 {len(pruned)}개 잘라냄: " + ", ".join(pruned), WARN)
    assign_ids(tree)
    omissions = [i for i in res.issues if i.rule.startswith("omission")]     # LLM 판정은 다시 부르지 않고 마지막 검사 결과를 쓴다
    return tree, [str(i) for i in check_tree(tree, spec_text) + omissions], pruned


# ③④ TC 생성 ⇄ TC 검사

def _finish(tc: TestCase, status: str, issues) -> TestCase:
    tc.status = status
    tc.notes = [str(i) for i in issues]
    return tc


def _generate_one(req: Requirement, outline: Outline, no: int, llm: LLMClient, trace: Trace) -> TestCase:
    """TC 하나를 쓰고, 통과할 때까지 검사-재작성을 돈다."""
    tag = f"TC#{no} '{outline.subject}'"
    first = write(req, outline, no, llm)
    trace.add("tc_build", f"{tag} 작성 (스텝 {len(first.steps)}줄, 기대결과 {len(first.expected)}줄)")

    def check(tc: TestCase):
        issues = check_tc(tc, req, llm)
        major = [i for i in issues if i.severity == "major"]
        if not major:
            trace.add("tc_check", f"{tag} PASS" + (f" (비고 {len(issues)}건)" if issues else ""))
        else:
            trace.add("tc_check", f"{tag} 문제 {len(major)}건: " + "; ".join(str(i) for i in major))
        return issues

    def revise(tc: TestCase, major):
        new = write(req, outline, no, llm, previous=tc, feedback=[str(i) for i in major])
        trace.add("tc_build", f"{tag} 지적 사항을 붙여 {new.revisions}회차 재작성")
        return new

    res = run_gate(first, check, revise)
    if res.passed:
        return _finish(res.output, "PASS", res.issues)                  # minor 이슈는 비고로 남는다
    majors = [str(i) for i in res.major]
    log.warning("TC#%d 재작성 %d회 후에도 실패: %s", no, res.revisions, majors)
    trace.add("tc_check", f"{tag} 재작성 {res.revisions}회 후에도 문제 남음 → FAIL: " + "; ".join(majors), WARN)
    return _finish(res.output, "FAIL", res.issues)


def stage_tc(tree: FeatureNode, spec_text: str, llm: LLMClient, trace: Trace
             ) -> tuple[list[Requirement], list[Gap], list[TestCase], list[dict], dict[str, list[int]]]:
    """(요구사항, 공백, TC, 계획에서 일부러 뺀 시나리오, 미대응 AC)."""
    requirements, gaps = derive_requirements(tree, spec_text, llm, trace.logger("tc_build"))
    trace.add("tc_build", f"요구사항 {len(requirements)}개, 공백 {len(gaps)}개")

    test_cases: list[TestCase] = []
    excluded: list[dict] = []
    for req in requirements:
        outlines, excl = plan(req, llm)
        excluded += [{"ri": req.id, "path": req.path, **e} for e in excl]
        trace.add("tc_build", f"{req.id} {' > '.join(req.path)}: AC {len(req.acs)}개 → TC 계획 {len(outlines)}건"
                              + (f", 뺀 시나리오 {len(excl)}건" if excl else ""))
        for outline in outlines:
            test_cases.append(_generate_one(req, outline, len(test_cases) + 1, llm, trace))

    uncovered = uncovered_acs(requirements, test_cases)
    for rid, idx in uncovered.items():
        req = next(r for r in requirements if r.id == rid)
        trace.add("tc_check", f"{rid} {' > '.join(req.path)}: AC {', '.join(str(i + 1) for i in idx)} 를 다루는 TC 없음", WARN)
    if not uncovered:
        trace.add("tc_check", "모든 AC 가 TC 에 대응됨")
    return requirements, gaps, test_cases, excluded, uncovered


def run(spec_text: str, llm: LLMClient, tree: FeatureNode | None = None,
        on_event: Callable[[Event], None] | None = None) -> PipelineResult:
    """spec_text: 기획서 원문. tree: 이미 분류 체계가 있으면 parse_markdown_tree 결과를 넘긴다(트리 생성·검사 생략).

    on_event: 실행 중에 단계별 기록을 바로 받고 싶을 때 넘긴다 (예: on_event=print).
    """
    trace = Trace(on_event)
    tree, tree_issues, pruned = stage_tree(spec_text, llm, tree, trace)
    requirements, gaps, test_cases, excluded, uncovered = stage_tc(tree, spec_text, llm, trace)

    stats = {
        "leaves": len(leaves(tree)),
        "defined": len(requirements),
        "gaps": len(gaps),
        "test_cases": len(test_cases),
        "pass": sum(t.status == "PASS" for t in test_cases),
        "fail": sum(t.status == "FAIL" for t in test_cases),
        "revised": sum(t.revisions > 0 for t in test_cases),
        "uncovered_acs": sum(len(v) for v in uncovered.values()),
        "pruned_nodes": len(pruned),
    }
    return PipelineResult(tree, test_cases, gaps, excluded, uncovered, tree_issues, pruned, stats,
                          trace.events, requirements)

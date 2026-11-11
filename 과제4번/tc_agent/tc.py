"""③ TC 생성: 트리의 leaf마다 요구사항(AC)을 뽑고, 계획하고, TC 를 쓴다. (만든 TC 를 검사하는 건 tc_check.py)

세 단계를 거친다. 한 번에 다 쓰게 하지 않고 나눈 이유는, 계획은 요구사항 전체를 보고 개수와 중복을 정해야 하고
작성은 TC 하나에만 집중해야 품질이 안정되기 때문이다. 다시 쓸 때도 TC 하나만 돌리면 되니 비용이 작다.

  derive_requirements : leaf -> Requirement(AC) | Gap(공백)      prompts/requirements.md
  plan                : 요구사항 -> TC 목록(outline)만 먼저      prompts/plan.md
  write               : outline 하나 -> TC 한 건 (재작성 겸용)    prompts/write.md

leaf 하나의 결과는 둘 중 하나다.
  Requirement: 기획서에 동작이 적혀 있어서 AC 를 뽑았다 -> TC 를 만든다
  Gap        : 기능은 있는데 동작이 안 적혀 있다 -> TC 를 만들지 않고 "기획 확인 필요"로 올린다

AC 에 든 수치도 기획서에 있어야 한다. 없으면 지적 사항을 붙여 다시 뽑게 하고, 그래도 남으면 그 AC 만 버린다.
"""
from __future__ import annotations

import json
from typing import Callable

from . import prompts
from .gate import run_gate
from .llm import LLMClient, parse_json
from .models import PRIORITIES, SCENARIOS, FeatureNode, Gap, Issue, Outline, Requirement, TestCase
from .tc_check import numbers_of
from .tree import leaves
from .trace import WARN

_NO_SPEC_REASON = "AC 가 입력되지 않았고 기획서도 없어 도출하지 못함"


# leaf -> 요구사항

def _ungrounded(acs: list[str], spec: str) -> dict[str, list[str]]:
    """원문에 없는 수치가 든 AC 와 그 수치."""
    allowed = numbers_of(spec)
    bad = {}
    for ac in acs:
        extra = sorted(n for n in numbers_of(ac) if n not in allowed)
        if extra:
            bad[ac] = extra
    return bad


def _acs_of(data: dict) -> list[str]:
    return [a for a in (str(x).strip() for x in data.get("acs", [])) if a]


def _call(spec: str, node: FeatureNode, path: list[str], llm: LLMClient,
          previous: dict | None = None, feedback: list[str] | None = None) -> dict:
    payload: dict = {"spec": spec, "leaf": {"path": path, "quote": node.quote}}
    if previous is not None:
        payload["previous"] = previous
        payload["revise_feedback"] = feedback or []
    return parse_json(llm.complete(prompts.REQ_SYSTEM, json.dumps(payload, ensure_ascii=False)))


def _derive_leaf(node: FeatureNode, path: list[str], spec: str, llm: LLMClient,
                 log: Callable[..., None]) -> Requirement | Gap:
    def check(data: dict) -> list[Issue]:
        if data.get("status") != "정의됨":
            return []
        return [Issue("ungrounded_number", "major", f"AC '{ac}' 의 수치 {nums} 가 기획서에 없음 — 원문 수치로 고치거나 이 AC 를 빼세요")
                for ac, nums in _ungrounded(_acs_of(data), spec).items()]

    def revise(data: dict, major: list[Issue]) -> dict:
        log(f"{node.id} {node.name}: 원문에 없는 수치 → AC 재도출")
        return _call(spec, node, path, llm, previous=data, feedback=[i.message for i in major])

    data = run_gate(_call(spec, node, path, llm), check, revise).output
    bad = _ungrounded(_acs_of(data), spec) if data.get("status") == "정의됨" else {}
    if bad:
        log(f"{node.id} {node.name}: 끝내 원문에 없는 수치가 남은 AC {len(bad)}개 삭제", WARN)
    acs = [a for a in _acs_of(data) if a not in bad]
    if data.get("status") != "정의됨" or not acs:
        return Gap(node.id, path, str(data.get("reason") or "").strip() or "기획서에 동작이 정의되지 않음")
    priority = data.get("priority") if data.get("priority") in PRIORITIES else (node.priority or "P1")
    return Requirement(id=node.id, path=path, title=node.name, acs=acs,
                       hints=[str(h) for h in data.get("hints", []) if str(h).strip()], priority=priority)


def derive_requirements(root: FeatureNode, spec: str, llm: LLMClient,
                        log: Callable[..., None] | None = None) -> tuple[list[Requirement], list[Gap]]:
    """leaf마다 요구사항 또는 공백을 만든다. log 를 주면 leaf별 결과를 한 줄씩 알린다."""
    log = log or (lambda *_a, **_k: None)
    reqs: list[Requirement] = []
    gaps: list[Gap] = []
    for node, path in leaves(root):
        label = f"{node.id} {' > '.join(path)}"
        if node.acs:                          # 마크다운으로 AC 를 직접 적어 뒀으면 그대로 쓴다
            reqs.append(Requirement(node.id, path, node.name, list(node.acs), list(node.hints), node.priority or "P1"))
            log(f"{label} → 요구사항 (입력된 AC {len(node.acs)}개 그대로)")
        elif not spec.strip():
            gaps.append(Gap(node.id, path, _NO_SPEC_REASON))
            log(f"{label} → 공백: {_NO_SPEC_REASON}", WARN)
        else:
            r = _derive_leaf(node, path, spec, llm, log)
            if isinstance(r, Requirement):
                reqs.append(r)
                log(f"{label} → 요구사항 (AC {len(r.acs)}개, {r.priority})")
            else:
                gaps.append(r)
                log(f"{label} → 공백: {r.reason}", WARN)
    return reqs, gaps


# 요구사항 -> 계획 -> TC

def plan(req: Requirement, llm: LLMClient) -> tuple[list[Outline], list[dict]]:
    payload = {"requirement": {"id": req.id, "path": req.path, "title": req.title, "acs": req.acs,
                                "hints": req.hints, "priority": req.priority}}
    data = parse_json(llm.complete(prompts.PLAN_SYSTEM, json.dumps(payload, ensure_ascii=False)))
    outlines = []
    for o in data.get("outline", []):
        covers = [i for i in o.get("covers", []) if isinstance(i, int) and 0 <= i < len(req.acs)]
        outlines.append(Outline(
            subject=str(o.get("subject", "")).strip(),
            scenario=o.get("scenario") if o.get("scenario") in SCENARIOS else "정상",
            priority=o.get("priority") if o.get("priority") in PRIORITIES else req.priority,
            covers=covers,
        ))
    return outlines, data.get("excluded", [])


def write(req: Requirement, outline: Outline, no: int, llm: LLMClient,
          previous: TestCase | None = None, feedback: list[str] | None = None) -> TestCase:
    """outline 하나를 TC 로 채운다. previous 와 feedback 을 주면 그 TC 를 고쳐 쓴다."""
    payload: dict = {
        "path": req.path,
        "source": {"title": req.title, "acs": req.acs, "hints": req.hints},
        "outline": outline.__dict__,
    }
    if previous is not None:
        payload["previous"] = {"precondition": previous.precondition, "steps": previous.steps,
                               "expected": previous.expected}
        payload["revise_feedback"] = feedback or []
    d = parse_json(llm.complete(prompts.WRITE_SYSTEM, json.dumps(payload, ensure_ascii=False)))
    return TestCase(
        no=no, ri=req.id, path=list(req.path), subject=outline.subject, scenario=outline.scenario,
        priority=outline.priority, covers=list(outline.covers),
        precondition=str(d.get("precondition") or "없음"),
        steps=[str(s) for s in d.get("steps", [])],
        expected=[str(s) for s in d.get("expected", [])],
        revisions=(previous.revisions + 1) if previous else 0,
    )

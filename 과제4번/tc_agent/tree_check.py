"""② 트리 검사: 만든 트리가 쓸 만한지 본다. 트리가 틀리면 아래 단계가 전부 틀어지므로 TC 를 만들기 전에 거른다.

세 가지를 본다.
  지어냄  모든 노드는 기획서에서 따온 문장(quote)을 달고 있어야 하고, 그 문장이 기획서에 정말 있어야 한다. (코드)
  누락    기획서 문장 중 어느 노드의 quote 에도 안 들어간 것을 코드가 추리고, 그게 빠진 기능인지는 LLM 이 판정한다.
  모양    깊이, 빈 이름, 같은 이름의 형제, 자식 하나뿐인 노드. (코드)

누락은 "문장이 어느 노드에도 안 걸렸다"까지만 코드가 알 수 있다. 그 문장이 기능 설명인지, 이미 있는 노드의 일부인지는
의미 판단이라 LLM(prompts/tree_check.md)에 맡긴다. 이 판정은 같은 계열 모델이 하므로 틀릴 수 있다.
"""
from __future__ import annotations

import json
import re

from . import prompts
from .llm import LLMClient, parse_json
from .models import FeatureNode, Issue
from .tree import walk

MAX_DEPTH = 3                 # 루트 아래 대/중/소분류까지
_MIN_SENTENCE = 6             # 이보다 짧은 조각은 문장으로 보지 않는다


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# 모양

def structure_issues(root: FeatureNode) -> list[Issue]:
    issues: list[Issue] = []
    for node, depth, path in walk(root):
        if depth == 0:
            continue
        label = " > ".join(path)
        if not node.name:
            issues.append(Issue("empty_name", "major", f"이름이 없는 노드 (상위: {' > '.join(path[:-1]) or '루트'})"))
            continue
        if depth > MAX_DEPTH:
            issues.append(Issue("depth_exceeded", "major", f"'{label}' 가 {MAX_DEPTH}단계를 넘음"))
        if len(node.children) == 1:
            issues.append(Issue("single_child", "minor", f"'{label}' 의 자식이 1개뿐 — 단계를 줄일 것"))
    for node, _d, path in walk(root):
        names = [c.name for c in node.children if c.name]
        for dup in sorted({n for n in names if names.count(n) > 1}):
            issues.append(Issue("duplicate_sibling", "major", f"'{' > '.join(path + [dup])}' 이름이 같은 형제 노드가 있음"))
    return issues


# 지어냄

def quote_issues(root: FeatureNode, spec: str) -> list[Issue]:
    issues: list[Issue] = []
    spec_n = _norm(spec)
    for node, depth, path in walk(root):
        if depth == 0 or not node.name:
            continue
        label = " > ".join(path)
        if not node.quote:
            issues.append(Issue("quote_missing", "major", f"'{label}' 에 원문 인용이 없음"))
        elif _norm(node.quote) not in spec_n:
            issues.append(Issue("quote_missing", "major", f"'{label}' 의 인용이 기획서에 없음 — 지어낸 기능이면 삭제할 것"))
    return issues


def prune_ungrounded(root: FeatureNode, spec: str) -> list[str]:
    """원문 근거가 없는 노드를 하위 트리째 잘라내고, 잘라낸 경로를 돌려준다. (검사를 끝내 못 넘겼을 때만 쓴다)"""
    spec_n = _norm(spec)
    pruned: list[str] = []

    def grounded(n: FeatureNode) -> bool:
        return bool(n.name) and bool(n.quote) and _norm(n.quote) in spec_n

    def rec(node: FeatureNode, path: list[str]):
        keep = []
        for c in node.children:
            if grounded(c):
                keep.append(c)
                rec(c, path + [c.name])
            else:
                pruned.append(" > ".join(path + [c.name or "(이름 없음)"]))
        node.children = keep
    rec(root, [])
    return pruned


# 누락

def sentences_of(spec: str) -> list[str]:
    """기획서를 문장 단위로 쪼갠다. 제목 줄(#)은 기능 설명이 아니라서 뺀다."""
    out = []
    for line in spec.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for s in re.split(r"(?<=[.!?。])\s+", line):
            s = _norm(s)
            if len(s) >= _MIN_SENTENCE:
                out.append(s)
    return out


def uncovered_sentences(root: FeatureNode, spec: str) -> list[str]:
    """어느 노드의 quote 에도 포함되지 않은 기획서 문장. 빠진 기능의 후보일 뿐 확정이 아니다."""
    quotes = [_norm(n.quote).rstrip(".") for n, _d, _p in walk(root) if n.quote]
    out = []
    for s in sentences_of(spec):
        core = s.rstrip(".")
        if not any(q in core or core in q for q in quotes):
            out.append(s)
    return out


def _outline(root: FeatureNode) -> list[str]:
    return ["  " * (d - 1) + f"{n.name} | {n.quote}" for n, d, _p in walk(root) if d > 0]


def omission_issues(root: FeatureNode, spec: str, llm: LLMClient) -> list[Issue]:
    """안 걸린 문장이 있으면 LLM 에게 빠진 기능인지 묻는다. 걸린 게 없으면 LLM 을 부르지 않는다."""
    cands = uncovered_sentences(root, spec)
    if not cands:
        return []
    payload = {"tree": _outline(root), "sentences": cands}
    try:
        data = parse_json(llm.complete(prompts.TREE_CHECK_SYSTEM, json.dumps(payload, ensure_ascii=False)))
    except ValueError as e:
        # 판정이 깨졌다고 트리를 통과시키지도 막지도 않는다. 비고에만 남겨 사람이 보게 한다.
        return [Issue("omission_check_error", "minor", f"누락 판정 응답 파싱 실패: {e} (후보 문장 {len(cands)}개 미확인)")]
    issues = []
    for v in data.get("verdicts", []):
        i = v.get("index")
        if isinstance(i, int) and 0 <= i < len(cands) and v.get("verdict") == "누락":
            reason = str(v.get("reason") or "").strip()
            issues.append(Issue("omission", "major",
                                f"기획서 문장 '{cands[i]}' 를 다루는 노드가 없음 — 기능 노드를 추가할 것"
                                + (f" ({reason})" if reason else "")))
    return issues


# 전체

def check_tree(root: FeatureNode, spec: str, llm: LLMClient | None = None) -> list[Issue]:
    """지어냄 + 모양을 먼저 보고, llm 을 주면 누락까지 본다. 코드로 잡히는 큰 문제가 있으면 LLM 판정은 아낀다."""
    issues = quote_issues(root, spec) + structure_issues(root)
    if llm is not None and not any(i.severity == "major" for i in issues):
        issues += omission_issues(root, spec, llm)
    return issues

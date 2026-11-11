"""① 트리 생성: 기획서에서 기능분류트리를 만든다. (만든 트리를 검사하는 건 tree_check.py)

기획서에서 요구사항을 바로 뽑으면 "뽑힌 것"만 보이고 빠진 기능은 알 수가 없다. 그래서 먼저 기능을 트리로 정리하고,
이후 단계는 전부 이 트리의 leaf를 기준으로 돈다.

트리를 얻는 길은 두 가지다.
  derive_tree         : 자유 서술 기획서에서 LLM 으로 도출 (prompts/tree.md)
  parse_markdown_tree : 이미 분류 체계가 있으면 마크다운으로 직접 입력 (LLM 안 씀, 검사도 건너뜀)
"""
from __future__ import annotations

import json
import re
from typing import Iterator

from . import prompts
from .llm import LLMClient, parse_json
from .models import PRIORITIES, FeatureNode


# 순회

def walk(root: FeatureNode) -> Iterator[tuple[FeatureNode, int, list[str]]]:
    """(노드, 깊이, 경로)를 차례로 돌려준다. 루트는 깊이 0이고 경로에는 들어가지 않는다."""
    def rec(node: FeatureNode, depth: int, path: list[str]):
        yield node, depth, path
        for c in node.children:
            yield from rec(c, depth + 1, path + [c.name])
    yield from rec(root, 0, [])


def leaves(root: FeatureNode) -> list[tuple[FeatureNode, list[str]]]:
    return [(n, p) for n, d, p in walk(root) if d > 0 and n.is_leaf]


def assign_ids(root: FeatureNode) -> None:
    def rec(node: FeatureNode, prefix: str):
        for i, c in enumerate(node.children, 1):
            c.id = f"{prefix}.{i}" if prefix else f"F{i}"
            rec(c, c.id)
    rec(root, "")


def tree_to_dict(node: FeatureNode) -> dict:
    d: dict = {"name": node.name}
    if node.quote:
        d["quote"] = node.quote
    if node.children:
        d["children"] = [tree_to_dict(c) for c in node.children]
    return d


def _from_dict(d: dict) -> FeatureNode:
    return FeatureNode(
        name=str(d.get("name", "")).strip(),
        quote=str(d.get("quote", "")).strip(),
        children=[_from_dict(c) for c in d.get("children", []) if isinstance(c, dict)],
    )


# LLM 으로 도출

def derive_tree(spec: str, llm: LLMClient, previous: FeatureNode | None = None,
                feedback: list[str] | None = None) -> FeatureNode:
    """previous 와 feedback 을 주면 그 트리에서 지적된 부분만 고친다."""
    payload: dict = {"spec": spec}
    if previous is not None:
        payload["previous"] = tree_to_dict(previous)
        payload["revise_feedback"] = feedback or []
    data = parse_json(llm.complete(prompts.TREE_SYSTEM, json.dumps(payload, ensure_ascii=False)))
    return _from_dict(data)


# 마크다운으로 직접 입력

_PRIORITY_SUFFIX = re.compile(r"\s*\[(P[012])\]\s*$")


def parse_markdown_tree(text: str) -> FeatureNode:
    """들여쓰기 목록으로 쓴 트리를 읽는다. leaf 아래 `AC:` `HINT:` 줄은 그 leaf의 요구사항이 된다.

        # 비밀번호 로그인                  <- 루트
        - 로그인                            <- 대분류
          - 계정 잠금 [P0]                  <- leaf, 우선순위는 이름 뒤 [P0]
            - AC: 5회 연속 틀리면 30분간 잠긴다
            - HINT: 4회 실패 후 성공하면 횟수 초기화
    """
    root: FeatureNode | None = None
    stack: list[tuple[int, FeatureNode]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if raw.lstrip().startswith("# ") and root is None:
            root = FeatureNode(name=raw.lstrip()[2:].strip())
            stack = [(-1, root)]
            continue
        if root is None or not raw.lstrip().startswith("- "):
            continue
        indent = len(raw) - len(raw.lstrip())
        body = raw.lstrip()[2:].strip()
        cur = stack[-1][1]
        if body.startswith("AC:"):
            cur.acs.append(body[3:].strip())
            continue
        if body.startswith("HINT:"):
            cur.hints.append(body[5:].strip())
            continue
        m = _PRIORITY_SUFFIX.search(body)
        node = FeatureNode(name=_PRIORITY_SUFFIX.sub("", body), priority=m.group(1) if m else "")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1].children.append(node)
        stack.append((indent, node))
    if root is None:
        raise ValueError("루트('# 이름') 줄이 없음")
    for node, _d, _p in walk(root):
        if node.priority and node.priority not in PRIORITIES:
            node.priority = ""
    assign_ids(root)
    return root

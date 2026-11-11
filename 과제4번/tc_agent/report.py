"""결과 출력: JSON(기계용) + Markdown(리뷰용)."""
from __future__ import annotations

import json

from .models import FeatureNode, PipelineResult
from .trace import STAGES
from .tree import tree_to_dict


def to_json(result: PipelineResult) -> str:
    return json.dumps({
        "stats": result.stats,
        "tree": tree_to_dict(result.tree),
        "requirements": [r.__dict__ for r in result.requirements],
        "gaps": [g.__dict__ for g in result.gaps],
        "uncovered_acs": result.uncovered_acs,
        "tree_issues": result.tree_issues,
        "pruned": result.pruned,
        "excluded": result.excluded,
        "test_cases": [t.to_dict() for t in result.test_cases],
        "trace": [{"stage": e.stage, "level": e.level, "message": e.message} for e in result.trace],
    }, ensure_ascii=False, indent=2)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def _tree_lines(node: FeatureNode, tc_count: dict[str, int], gap_ids: set[str], depth: int = 0) -> list[str]:
    out = []
    for c in node.children:
        mark = ""
        if c.is_leaf:
            mark = f" — {'⚠ 공백(기획 확인 필요)' if c.id in gap_ids else f'TC {tc_count.get(c.id, 0)}건'}"
        out.append(f"{'  ' * depth}- {c.name}{mark}")
        out += _tree_lines(c, tc_count, gap_ids, depth + 1)
    return out


def _stage_summary(result: PipelineResult) -> dict[str, str]:
    """단계별 결과를 한 줄로. stats 에서 바로 나오는 값만 쓴다."""
    s = result.stats
    return {
        "tree_build": f"leaf {s['leaves']}개",
        "tree_check": f"근거 없어 잘라낸 노드 {s['pruned_nodes']}개, 남은 문제 {len(result.tree_issues)}건",
        "tc_build": f"요구사항 {s['defined']}개 / 공백 {s['gaps']}개 → TC {s['test_cases']}건"
                    + (f" (뺀 시나리오 {len(result.excluded)}건)" if result.excluded else ""),
        "tc_check": f"PASS {s['pass']} / FAIL {s['fail']}, 재작성한 TC {s['revised']}건, 미대응 AC {s['uncovered_acs']}건",
    }


def to_flow_markdown(result: PipelineResult, log: bool = True) -> str:
    """실행 흐름: 단계별 결과 요약표, log=True 면 일어난 순서대로의 기록도. ⚠ 는 사람이 볼 만한 일."""
    summary = _stage_summary(result)
    warns = {key: sum(e.level == "warn" for e in result.trace if e.stage == key) for key, _ in STAGES}
    out = ["## 실행 흐름", "", "| 단계 | 결과 | ⚠ |", "|---|---|---|"]
    out += [f"| {label} | {summary[key]} | {warns[key] or ''} |" for key, label in STAGES]
    if log:
        out += ["", "일어난 순서대로:", "", "```"]
        out += [str(e) for e in result.trace]
        out += ["```"]
    out.append("")
    return "\n".join(out)


def to_markdown(result: PipelineResult) -> str:
    out = [
        "# TC 생성 결과", "",
        to_flow_markdown(result, log=False),
        f"## 기능분류트리 — {result.tree.name}", "",
    ]
    tc_count: dict[str, int] = {}
    for t in result.test_cases:
        tc_count[t.ri] = tc_count.get(t.ri, 0) + 1
    out += _tree_lines(result.tree, tc_count, {g.id for g in result.gaps})

    out += ["", "## 테스트케이스", "",
            "| No | 대분류 | 중분류 | 소분류 | 서브젝트 | 시나리오 | 우선순위 | 사전조건 | 테스트스텝 | 기대결과 | 상태 | 비고 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in result.test_cases:
        p = (t.path + ["", "", ""])[:3]
        out.append("| " + " | ".join(_cell(x) for x in [
            str(t.no), *p, t.subject, t.scenario, t.priority, t.precondition,
            "\n".join(t.steps), "\n".join(t.expected),
            t.status + (f" (재작성 {t.revisions})" if t.revisions else ""), "\n".join(t.notes),
        ]) + " |")

    if result.gaps:
        out += ["", "## 기획 확인 필요 (공백)", ""]
        out += [f"- {' > '.join(g.path)}: {g.reason}" for g in result.gaps]
    if result.uncovered_acs:
        out += ["", "## 미대응 AC", ""]
        out += [f"- {rid}: AC {', '.join(str(i + 1) for i in idx)}" for rid, idx in result.uncovered_acs.items()]
    if result.excluded:
        out += ["", "## 일부러 뺀 시나리오", ""]
        out += [f"- {' > '.join(e['path'])} / {e.get('scenario', '')}: {e.get('reason', '')}" for e in result.excluded]
    if result.pruned or result.tree_issues:
        out += ["", "## 트리 검사에서 남은 문제", ""]
        out += [f"- 근거가 없어 잘라낸 노드: {p}" for p in result.pruned]
        out += [f"- {i}" for i in result.tree_issues]
    return "\n".join(out) + "\n"

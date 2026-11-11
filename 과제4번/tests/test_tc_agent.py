import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from tc_agent import gate, pipeline, prompts, report, tree, tree_check
from tc_agent import tc as tc_gen
from tc_agent.llm import parse_json
from tc_agent.models import Issue, Requirement, TestCase
from tc_agent.tc_check import check_rules
from tc_agent.trace import STAGES, WARN, Trace

EX = Path(__file__).parents[1] / "examples"
SPEC = (EX / "sample_spec.md").read_text(encoding="utf-8")

REQ = Requirement("F1.2", ["로그인", "계정 잠금"], "계정 잠금", ["비밀번호를 5회 연속 틀리면 30분간 잠긴다"], [], "P0")


def tc(**kw) -> TestCase:
    base = dict(no=1, ri="F1.2", path=["로그인", "계정 잠금"], subject="5회 실패 시 잠김", scenario="경계",
                priority="P0", precondition="없음", steps=["1. 진입", "2. 5회 틀리게 입력"],
                expected=["30분간 잠김 안내가 노출됨"])
    base.update(kw)
    return TestCase(**base)


# ── 테스트 전용 스텁 ─────────────────────────────────────────────────────────

def node(name, quote="", *children):
    d = {"name": name, "quote": quote}
    if children:
        d["children"] = list(children)
    return d


GOOD_TREE = {"name": "비밀번호 로그인", "children": [
    node("로그인", "사용자는 아이디와 비밀번호를 입력해 로그인한다",
         node("로그인 성공", "올바른 비밀번호를 입력하면 메인 화면으로 이동한다"),
         node("계정 잠금", "비밀번호를 5회 연속 틀리면 계정이 30분간 잠긴다")),
    node("로그인 상태 유지", "로그인 상태 유지를 선택하면 앱을 다시 열어도 로그인이 유지된다",
         node("상태 유지 선택", "로그인 상태 유지를 선택하면 앱을 다시 열어도 로그인이 유지된다"),
         node("로그아웃", "로그아웃하면 유지된 로그인 정보가 삭제된다")),
    node("비밀번호 재설정", "비밀번호 재설정은 추후 정의 예정이다"),
]}
FAKE_NODE = node("지문 로그인", "지문으로도 로그인할 수 있다")        # 기획서에 없는 기능
TREE_WITH_FAKE = {**GOOD_TREE, "children": GOOD_TREE["children"] + [FAKE_NODE]}
# 로그인 상태 유지 그룹을 통째로 빠뜨린 트리 (기획서의 해당 문장 2개가 어느 노드에도 안 걸린다)
TREE_MISSING_KEEP = {**GOOD_TREE, "children": [GOOD_TREE["children"][0], GOOD_TREE["children"][2]]}
OMIT_KEYWORDS = ["로그인 상태 유지", "로그아웃하면"]

REQ_BY_QUOTE = {                                   # leaf quote → 요구사항 응답
    "올바른 비밀번호를 입력하면 메인 화면으로 이동한다":
        {"status": "정의됨", "priority": "P0", "acs": ["올바른 비밀번호를 입력하면 메인 화면으로 이동한다"], "hints": []},
    "비밀번호를 5회 연속 틀리면 계정이 30분간 잠긴다":
        {"status": "정의됨", "priority": "P0", "acs": ["5회 연속 틀리면 30분간 잠긴다", "잠긴 계정은 안내 문구를 노출한다"], "hints": []},
    "로그인 상태 유지를 선택하면 앱을 다시 열어도 로그인이 유지된다":
        {"status": "정의됨", "priority": "P1", "acs": ["상태 유지 선택 시 재실행해도 로그인 유지"], "hints": []},
    "로그아웃하면 유지된 로그인 정보가 삭제된다":
        {"status": "정의됨", "priority": "P1", "acs": ["로그아웃하면 유지된 정보가 삭제된다"], "hints": []},
    "비밀번호 재설정은 추후 정의 예정이다":
        {"status": "공백", "priority": "P2", "acs": [], "hints": [], "reason": "재설정 동작이 정의되지 않음"},
}
GOOD_TC = {"precondition": "없음", "steps": ["1. 진입", "2. 입력"], "expected": ["기대한 결과가 노출됨"]}
BAD_TC = {"precondition": "없음", "steps": ["1. 진입"] * 7, "expected": ["버튼 폭 120px 로 노출됨"]}


class ScriptedLLM:
    """프롬프트로 단계를 구분해 정해진 JSON 을 돌려주는 테스트 전용 스텁."""

    def __init__(self, trees, req_by_quote=None, tc_outputs=None, omit_keywords=None):
        self.trees = list(trees)                  # 호출 순서대로 쓰고 마지막 값을 반복
        self.req_by_quote = req_by_quote if req_by_quote is not None else REQ_BY_QUOTE
        self.tc_outputs = tc_outputs or [GOOD_TC]
        self.omit_keywords = omit_keywords or []  # 이 말이 든 문장은 트리 검사에서 "누락"으로 판정
        self.calls = {"tree": 0, "check": 0, "req": 0, "write": 0}
        self.req_overrides: list[dict] = []       # 요구사항 호출에 먼저 쓸 응답

    def complete(self, system, user):
        p = json.loads(user)
        if system is prompts.TREE_SYSTEM:
            out = self.trees[min(self.calls["tree"], len(self.trees) - 1)]
            self.calls["tree"] += 1
            return json.dumps(out, ensure_ascii=False)
        if system is prompts.TREE_CHECK_SYSTEM:
            self.calls["check"] += 1
            verdicts = [{"index": i, "verdict": "누락" if any(k in s for k in self.omit_keywords) else "포함됨",
                         "node": "", "reason": "기능 설명"} for i, s in enumerate(p["sentences"])]
            return json.dumps({"verdicts": verdicts}, ensure_ascii=False)
        if system is prompts.REQ_SYSTEM:
            self.calls["req"] += 1
            if self.req_overrides:
                return json.dumps(self.req_overrides.pop(0), ensure_ascii=False)
            return json.dumps(self.req_by_quote[p["leaf"]["quote"]], ensure_ascii=False)
        if system is prompts.PLAN_SYSTEM:
            r = p["requirement"]
            outline = [{"subject": f"AC{i + 1} 확인", "scenario": "정상", "priority": r["priority"], "covers": [i]}
                       for i in range(len(r["acs"]))]
            return json.dumps({"outline": outline, "excluded": []}, ensure_ascii=False)
        if system is prompts.WRITE_SYSTEM:
            out = self.tc_outputs[min(self.calls["write"], len(self.tc_outputs) - 1)]
            self.calls["write"] += 1
            return json.dumps(out, ensure_ascii=False)
        if system is prompts.JUDGE_SYSTEM:
            ok = {"verdict": "PASS", "reason": ""}
            return json.dumps({"correctness": ok, "completeness": ok, "clarity": ok})
        raise AssertionError("알 수 없는 단계")


def parsed(d):
    return tree._from_dict(d)


# ── 공통 루프 ────────────────────────────────────────────────────────────────

def major(msg="문제"):
    return Issue("x", "major", msg)


class GateTests(unittest.TestCase):
    def test_passes_without_revising(self):
        res = gate.run_gate("a", check=lambda o: [], revise=lambda o, m: self.fail("고치면 안 됨"))
        self.assertEqual((res.output, res.passed, res.revisions), ("a", True, 0))

    def test_revises_until_it_passes(self):
        res = gate.run_gate(0, check=lambda n: [major()] if n < 2 else [], revise=lambda n, m: n + 1)
        self.assertEqual((res.output, res.passed, res.revisions), (2, True, 2))

    def test_stops_at_limit_and_reports_failure(self):
        res = gate.run_gate(0, check=lambda n: [major()], revise=lambda n, m: n + 1)
        self.assertEqual((res.passed, res.revisions, len(res.major)), (False, gate.MAX_REVISIONS, 1))

    def test_minor_issues_do_not_trigger_revision_but_are_kept(self):
        minor = Issue("note", "minor", "비고")
        res = gate.run_gate("a", check=lambda o: [minor], revise=lambda o, m: self.fail("고치면 안 됨"))
        self.assertEqual((res.passed, res.issues), (True, [minor]))

    def test_revise_receives_only_major_issues(self):
        seen = []
        gate.run_gate(0, check=lambda n: [Issue("n", "minor", "m"), major("M")] if n < 1 else [],
                      revise=lambda n, ms: seen.append([i.message for i in ms]) or n + 1)
        self.assertEqual(seen, [["M"]])

    def test_zero_limit_never_revises(self):
        res = gate.run_gate(0, check=lambda n: [major()], revise=lambda n, m: self.fail("고치면 안 됨"), max_revisions=0)
        self.assertEqual((res.passed, res.revisions), (False, 0))


# ── ④ 규칙·파서 ──────────────────────────────────────────────────────────────

class RuleTests(unittest.TestCase):
    def rules(self, **kw):
        return {i.rule for i in check_rules(tc(**kw), REQ)}

    def test_clean_tc_has_no_issue(self):
        self.assertEqual(self.rules(), set())

    def test_too_many_steps(self):
        self.assertIn("steps_too_long", self.rules(steps=[f"{n}. x" for n in range(1, 8)]))

    def test_style_value(self):
        self.assertIn("style_value", self.rules(expected=["버튼 폭 120px 로 노출됨"]))

    def test_loop_words(self):
        self.assertIn("loop_words", self.rules(steps=["1. 진입", "2. 위 절차를 반복"]))

    def test_ungrounded_number_detected(self):
        self.assertIn("ungrounded_number", self.rules(expected=["45분간 잠김"]))

    def test_grounded_number_and_enumerator_ok(self):
        self.assertEqual(self.rules(expected=["1. 5회 실패 후 30분간 잠김"]), set())

    def test_empty_fields(self):
        self.assertTrue({"empty_steps", "empty_expected"} <= self.rules(steps=[], expected=[]))


class ParseTests(unittest.TestCase):
    def test_parse_json_tolerates_fence_and_prose(self):
        self.assertEqual(parse_json('설명\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_parse_json_raises_without_json(self):
        with self.assertRaises(ValueError):
            parse_json("없음")

    def test_markdown_tree(self):
        root = tree.parse_markdown_tree((EX / "sample_tree.md").read_text(encoding="utf-8"))
        self.assertEqual(root.name, "비밀번호 로그인")
        lv = {n.name: (n.id, p, n.priority, len(n.acs)) for n, p in tree.leaves(root)}
        self.assertEqual(lv["계정 잠금"], ("F1.2", ["로그인", "계정 잠금"], "P0", 2))
        self.assertEqual(lv["비밀번호 재설정"][3], 0)
        self.assertEqual(len(root.children), 3)

    def test_markdown_tree_requires_root(self):
        with self.assertRaises(ValueError):
            tree.parse_markdown_tree("- 로그인")


# ── ② 트리 검사 ──────────────────────────────────────────────────────────────

class TreeCheckTests(unittest.TestCase):
    def rules(self, d):
        return {i.rule for i in tree_check.check_tree(parsed(d), SPEC)}

    def test_good_tree_has_no_major(self):
        issues = tree_check.check_tree(parsed(GOOD_TREE), SPEC)
        self.assertFalse([i for i in issues if i.severity == "major"])

    def test_invented_node_detected(self):
        self.assertIn("quote_missing", self.rules(TREE_WITH_FAKE))

    def test_missing_quote_detected(self):
        self.assertIn("quote_missing", self.rules({"name": "x", "children": [node("로그인", "")]}))

    def test_quote_matching_ignores_whitespace(self):
        d = {"name": "x", "children": [node("로그인", "사용자는   아이디와 비밀번호를\n입력해 로그인한다")]}
        self.assertNotIn("quote_missing", self.rules(d))

    def test_depth_duplicate_and_single_child(self):
        q = "사용자는 아이디와 비밀번호를 입력해 로그인한다"
        deep = {"name": "x", "children": [node("a", q, node("b", q, node("c", q, node("d", q))))]}
        self.assertIn("depth_exceeded", self.rules(deep))
        self.assertIn("single_child", self.rules(deep))
        dup = {"name": "x", "children": [node("로그인", q), node("로그인", q)]}
        self.assertIn("duplicate_sibling", self.rules(dup))

    def test_prune_removes_ungrounded_subtree(self):
        root = parsed(TREE_WITH_FAKE)
        self.assertEqual(tree_check.prune_ungrounded(root, SPEC), ["지문 로그인"])
        self.assertEqual(len(root.children), 3)


class OmissionCheckTests(unittest.TestCase):
    def test_headings_are_not_sentences(self):
        sents = tree_check.sentences_of(SPEC)
        self.assertFalse([s for s in sents if s.startswith("#") or "예시용 가상 문서" in s])
        self.assertIn("로그아웃하면 유지된 로그인 정보가 삭제된다.", sents)

    def test_complete_tree_leaves_only_detail_sentences_as_candidates(self):
        cands = tree_check.uncovered_sentences(parsed(GOOD_TREE), SPEC)
        self.assertEqual(cands, ["잠긴 계정으로 로그인하면 잠금 안내 문구를 노출한다.", "4회 실패 후 성공하면 실패 횟수가 초기화된다."])

    def test_missing_group_makes_more_candidates(self):
        cands = tree_check.uncovered_sentences(parsed(TREE_MISSING_KEEP), SPEC)
        self.assertTrue(any("로그아웃" in s for s in cands))
        self.assertTrue(any("로그인 상태 유지를 선택" in s for s in cands))

    def test_llm_verdict_turns_candidates_into_major_omission(self):
        llm = ScriptedLLM([], omit_keywords=OMIT_KEYWORDS)
        issues = tree_check.check_tree(parsed(TREE_MISSING_KEEP), SPEC, llm)
        self.assertEqual([i.rule for i in issues], ["omission", "omission"])
        self.assertTrue(all(i.severity == "major" for i in issues))

    def test_candidates_the_llm_calls_included_are_not_issues(self):
        llm = ScriptedLLM([])                                    # 아무것도 누락이라고 하지 않음
        self.assertEqual(tree_check.check_tree(parsed(GOOD_TREE), SPEC, llm), [])
        self.assertEqual(llm.calls["check"], 1)

    def test_llm_is_not_called_when_nothing_is_left_over(self):
        spec = "사용자는 로그인한다.\n"
        root = parsed({"name": "x", "children": [node("로그인", "사용자는 로그인한다")]})

        class Never:
            def complete(self, system, user):
                raise AssertionError("부르면 안 됨")
        self.assertEqual(tree_check.check_tree(root, spec, Never()), [])

    def test_llm_is_spared_when_code_already_found_a_major_problem(self):
        llm = ScriptedLLM([], omit_keywords=OMIT_KEYWORDS)
        tree_check.check_tree(parsed(TREE_WITH_FAKE), SPEC, llm)
        self.assertEqual(llm.calls["check"], 0)

    def test_broken_verdict_is_minor_and_does_not_block(self):
        class Broken:
            def complete(self, system, user):
                return "모르겠음"
        issues = tree_check.check_tree(parsed(GOOD_TREE), SPEC, Broken())
        self.assertEqual([(i.rule, i.severity) for i in issues], [("omission_check_error", "minor")])


# ── ① 트리 생성 + ② 트리 검사 (stage_tree) ────────────────────────────────────

class StageTreeTests(unittest.TestCase):
    def run_stage(self, llm):
        trace = Trace()
        return (*pipeline.stage_tree(SPEC, llm, None, trace), trace)

    def test_invented_node_is_fixed_by_regeneration(self):
        llm = ScriptedLLM([TREE_WITH_FAKE, GOOD_TREE])
        root, issues, pruned, _ = self.run_stage(llm)
        self.assertEqual((llm.calls["tree"], pruned), (2, []))
        self.assertEqual(len(root.children), 3)

    def test_invented_node_is_pruned_when_model_keeps_it(self):
        llm = ScriptedLLM([TREE_WITH_FAKE])
        root, issues, pruned, _ = self.run_stage(llm)
        self.assertEqual((llm.calls["tree"], pruned), (1 + gate.MAX_REVISIONS, ["지문 로그인"]))
        self.assertFalse([i for i in issues if "[major" in i])

    def test_missing_feature_is_fixed_by_regeneration(self):
        llm = ScriptedLLM([TREE_MISSING_KEEP, GOOD_TREE], omit_keywords=OMIT_KEYWORDS)
        root, issues, pruned, trace = self.run_stage(llm)
        self.assertEqual(llm.calls["tree"], 2)
        self.assertEqual(len(root.children), 3)
        self.assertTrue(any(e.stage == "tree_check" and "문제 2건" in e.message for e in trace.events))
        self.assertTrue(any(e.stage == "tree_build" and "1회차 재생성" in e.message for e in trace.events))

    def test_missing_feature_the_model_keeps_dropping_stays_in_issues(self):
        llm = ScriptedLLM([TREE_MISSING_KEEP], omit_keywords=OMIT_KEYWORDS)
        root, issues, pruned, trace = self.run_stage(llm)
        self.assertEqual(len(root.children), 2)                             # 코드는 빠진 걸 채우지 못한다
        self.assertEqual(len([i for i in issues if "omission" in i]), 2)    # 대신 사람이 볼 수 있게 남긴다
        self.assertTrue(any(e.level == WARN and e.stage == "tree_check" for e in trace.events))

    def test_ids_are_assigned_by_code(self):
        root, _, _, _ = self.run_stage(ScriptedLLM([GOOD_TREE]))
        self.assertEqual([n.id for n, _ in tree.leaves(root)], ["F1.1", "F1.2", "F2.1", "F2.2", "F3"])


# ── ③ 요구사항 도출 ──────────────────────────────────────────────────────────

class RequirementTests(unittest.TestCase):
    def setUp(self):
        self.root, _, _ = pipeline.stage_tree(SPEC, ScriptedLLM([GOOD_TREE]), None, Trace())[:3]

    def test_gap_leaf_becomes_gap_not_requirement(self):
        reqs, gaps = tc_gen.derive_requirements(self.root, SPEC, ScriptedLLM([GOOD_TREE]))
        self.assertEqual(len(reqs), 4)
        self.assertEqual([(g.id, g.path) for g in gaps], [("F3", ["비밀번호 재설정"])])

    def test_ungrounded_ac_number_is_revised(self):
        llm = ScriptedLLM([GOOD_TREE])
        llm.req_overrides = [{"status": "정의됨", "acs": ["올바른 비밀번호면 99초 안에 이동한다"], "hints": []}]
        reqs, _ = tc_gen.derive_requirements(self.root, SPEC, llm)
        first = next(r for r in reqs if r.id == "F1.1")
        self.assertEqual(first.acs, ["올바른 비밀번호를 입력하면 메인 화면으로 이동한다"])   # 2번째 호출이 정상 응답

    def test_ungrounded_ac_is_dropped_when_model_keeps_it(self):
        llm = ScriptedLLM([GOOD_TREE])
        bad = {"status": "정의됨", "acs": ["99초 안에 이동한다", "메인 화면으로 이동한다"], "hints": []}
        llm.req_overrides = [bad] * (1 + gate.MAX_REVISIONS)
        reqs, _ = tc_gen.derive_requirements(self.root, SPEC, llm)
        first = next(r for r in reqs if r.id == "F1.1")
        self.assertEqual(first.acs, ["메인 화면으로 이동한다"])

    def test_ac_less_leaf_without_spec_is_gap(self):
        root = tree.parse_markdown_tree((EX / "sample_tree.md").read_text(encoding="utf-8"))
        reqs, gaps = tc_gen.derive_requirements(root, "", ScriptedLLM([GOOD_TREE]))
        self.assertEqual((len(reqs), [g.id for g in gaps]), (4, ["F3"]))


# ── 파이프라인 ───────────────────────────────────────────────────────────────

class PipelineTests(unittest.TestCase):
    def test_end_to_end_inherits_tree_path_and_reports_gap(self):
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE]))
        self.assertEqual(res.stats["leaves"], 5)
        self.assertEqual((res.stats["defined"], res.stats["gaps"]), (4, 1))
        self.assertEqual(res.stats["test_cases"], 5)                    # AC 5개 → TC 5건
        self.assertTrue(all(t.status == "PASS" for t in res.test_cases))
        lock = [t for t in res.test_cases if t.ri == "F1.2"]
        self.assertTrue(lock and all(t.path == ["로그인", "계정 잠금"] for t in lock))
        self.assertEqual(res.uncovered_acs, {})
        md = report.to_markdown(res)
        self.assertIn("기획 확인 필요", md)
        self.assertIn("재설정 동작이 정의되지 않음", md)

    def test_gap_leaf_gets_no_test_case(self):
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE]))
        self.assertFalse([t for t in res.test_cases if t.ri == "F3"])

    def test_tc_are_made_only_after_the_tree_passes(self):
        res = pipeline.run(SPEC, ScriptedLLM([TREE_MISSING_KEEP, GOOD_TREE], omit_keywords=OMIT_KEYWORDS))
        self.assertEqual(res.stats["leaves"], 5)                        # 빠진 그룹이 채워진 트리로 TC 를 만든다
        stages = [e.stage for e in res.trace]
        self.assertLess(max(i for i, s in enumerate(stages) if s == "tree_check"),
                        min(i for i, s in enumerate(stages) if s == "tc_build"))

    def test_pruned_node_is_reported(self):
        res = pipeline.run(SPEC, ScriptedLLM([TREE_WITH_FAKE]))
        self.assertEqual(res.pruned, ["지문 로그인"])
        self.assertIn("근거가 없어 잘라낸 노드: 지문 로그인", report.to_markdown(res))

    def test_markdown_tree_input_skips_tree_generation_and_check(self):
        root = tree.parse_markdown_tree((EX / "sample_tree.md").read_text(encoding="utf-8"))
        llm = ScriptedLLM([GOOD_TREE])
        res = pipeline.run("", llm, tree=root)
        self.assertEqual((llm.calls["tree"], llm.calls["check"], llm.calls["req"]), (0, 0, 0))
        self.assertEqual((res.stats["defined"], res.stats["gaps"]), (4, 1))

    def test_defect_is_caught_and_rewritten(self):
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE], tc_outputs=[BAD_TC, GOOD_TC]))
        first = res.test_cases[0]
        self.assertEqual((first.status, first.revisions), ("PASS", 1))

    def test_exhausted_revisions_end_as_fail_with_notes(self):
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE], tc_outputs=[BAD_TC]))      # 수정 요청을 계속 무시
        self.assertTrue(all(t.status == "FAIL" and t.notes for t in res.test_cases))
        self.assertTrue(all(t.revisions == gate.MAX_REVISIONS for t in res.test_cases))

    def test_uncovered_ac_is_reported(self):
        class Forgetful(ScriptedLLM):                 # 계획에서 AC 하나를 빠뜨리는 모델
            def complete(self, system, user):
                out = super().complete(system, user)
                if system is prompts.PLAN_SYSTEM:
                    d = json.loads(out)
                    if len(d["outline"]) > 1:
                        d["outline"] = d["outline"][1:]
                    out = json.dumps(d, ensure_ascii=False)
                return out
        res = pipeline.run(SPEC, Forgetful([GOOD_TREE]))
        self.assertEqual(res.uncovered_acs, {"F1.2": [0]})
        self.assertIn("미대응 AC", report.to_markdown(res))


# ── 실행 흐름 기록 ───────────────────────────────────────────────────────────

class TraceTests(unittest.TestCase):
    def test_all_four_stages_are_recorded_in_flow_order(self):
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE]))
        seen = []
        for e in res.trace:                              # 처음 등장하는 순서
            if e.stage not in seen:
                seen.append(e.stage)
        self.assertEqual(seen, [k for k, _ in STAGES])

    def test_rewrite_is_traced_between_check_events(self):
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE], tc_outputs=[BAD_TC, GOOD_TC]))
        seq = [e.stage for e in res.trace if "TC#1 " in e.message]
        self.assertEqual(seq, ["tc_build", "tc_check", "tc_build", "tc_check"])   # 작성, 검사, 재작성, 검사

    def test_warn_events_mark_what_a_human_should_see(self):
        res = pipeline.run(SPEC, ScriptedLLM([TREE_WITH_FAKE], tc_outputs=[BAD_TC]))
        warns = {e.stage for e in res.trace if e.level == WARN}
        self.assertTrue({"tree_check", "tc_build", "tc_check"} <= warns)     # 잘라냄, 공백, FAIL

    def test_on_event_receives_events_while_running(self):
        got = []
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE]), on_event=got.append)
        self.assertEqual(got, res.trace)

    def test_direct_tree_input_is_traced(self):
        root = tree.parse_markdown_tree((EX / "sample_tree.md").read_text(encoding="utf-8"))
        res = pipeline.run("", ScriptedLLM([GOOD_TREE]), tree=root)
        self.assertIn("직접 입력", res.trace[0].message)

    def test_flow_report_and_json_include_trace(self):
        res = pipeline.run(SPEC, ScriptedLLM([GOOD_TREE]))
        md = report.to_markdown(res)
        self.assertIn("## 실행 흐름", md)
        self.assertIn("PASS 5 / FAIL 0", md)
        self.assertNotIn("일어난 순서대로", md)                       # 리포트에는 단계 요약만, 기록 전체는 to_flow_markdown
        self.assertIn("일어난 순서대로", report.to_flow_markdown(res))
        data = json.loads(report.to_json(res))
        self.assertEqual(len(data["trace"]), len(res.trace))
        self.assertEqual(sum(len(r["acs"]) for r in data["requirements"]), 5)      # 평가할 때 전체 AC 수를 센다

    def test_unknown_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            Trace().add("nope", "x")


# ── 프롬프트 파일 ────────────────────────────────────────────────────────────

class PromptFileTests(unittest.TestCase):
    # 코드가 응답에서 읽는 키. 프롬프트의 출력 스키마에서 빠지면 그 단계가 조용히 깨진다.
    READS = {
        "tree": ["name", "quote", "children"],                                         # tree._from_dict
        "tree_check": ["verdicts", "index", "verdict", "reason"],                      # tree_check.omission_issues
        "requirements": ["status", "priority", "acs", "hints", "reason"],              # tc._derive_leaf
        "plan": ["outline", "excluded", "subject", "scenario", "priority", "covers"],  # tc.plan
        "write": ["precondition", "steps", "expected"],                                # tc.write
        "judge": ["correctness", "completeness", "clarity", "verdict", "reason"],      # tc_check.judge
    }

    def test_constants_come_from_files(self):
        pairs = {"tree": prompts.TREE_SYSTEM, "tree_check": prompts.TREE_CHECK_SYSTEM,
                 "requirements": prompts.REQ_SYSTEM, "plan": prompts.PLAN_SYSTEM,
                 "write": prompts.WRITE_SYSTEM, "judge": prompts.JUDGE_SYSTEM}
        for name, const in pairs.items():
            self.assertEqual(const, prompts.load(name), name)
            self.assertTrue(const.strip(), name)

    def test_every_prompt_file_has_a_constant(self):
        files = {p.stem for p in (Path(prompts.__file__).parent).glob("*.md") if p.stem != "README"}
        self.assertEqual(files, set(self.READS))

    def test_each_prompt_names_the_keys_the_code_reads(self):
        for name, keys in self.READS.items():
            text = prompts.load(name)
            for key in keys:
                self.assertIn(f'"{key}"', text, f"{name}.md 의 출력 스키마에 '{key}' 가 없음")

    def test_missing_prompt_file_names_the_path(self):
        with self.assertRaises(FileNotFoundError) as cm:
            prompts.load("nope")
        self.assertIn("nope.md", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

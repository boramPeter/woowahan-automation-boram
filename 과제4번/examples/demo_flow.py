"""실제 모델 없이 흐름만 보는 데모. 테스트용 스텁 모델이 정해진 답을 주기 때문에 내용이 아니라 흐름을 보는 용도다.

    python3 examples/demo_flow.py

일부러 두 가지 문제를 섞었다.
  ① 첫 트리가 '로그인 상태 유지' 기능을 통째로 빠뜨림  -> ② 트리 검사가 누락을 잡고 ①을 다시 하게 함
  ③ 첫 TC 가 규칙을 어김                            -> ④ TC 검사가 잡고 ③을 다시 하게 함
실행 중에 단계 기록이 한 줄씩 나오고, 끝에 리포트의 "실행 흐름"이 출력된다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_tc_agent import (BAD_TC, GOOD_TC, GOOD_TREE, OMIT_KEYWORDS, SPEC,  # noqa: E402
                           TREE_MISSING_KEEP, ScriptedLLM)

from tc_agent import pipeline, report  # noqa: E402

llm = ScriptedLLM([TREE_MISSING_KEEP, GOOD_TREE], tc_outputs=[BAD_TC, GOOD_TC], omit_keywords=OMIT_KEYWORDS)
print("=== 실행 중 (on_event) ===")
result = pipeline.run(SPEC, llm, on_event=print)
print("\n=== 리포트의 실행 흐름 ===\n")
print(report.to_flow_markdown(result, log=False))

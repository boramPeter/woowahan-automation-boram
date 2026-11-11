# tc-agent-prototype

기획서에서 기능분류트리를 먼저 만들고, 트리가 제대로 나왔는지 확인한 다음, 그 트리로 테스트케이스(TC)를 만들고, TC도 한 번 더 확인하는 QA 도구 프로토타입입니다. 확인에서 걸린 것만 다시 만듭니다. 구조와 프롬프트를 어떻게 짰는지 보여 주려고 만들었습니다.

- 설계: [docs/DESIGN.md](docs/DESIGN.md)
- 평가 방법: [docs/EVALUATION.md](docs/EVALUATION.md)
- 앞으로 할 일(LLM Wiki·RAG, 일부러 뒤로 미룸): [docs/ROADMAP.md](docs/ROADMAP.md)

## 흐름

```
기획서
  │
  ▼
① 트리 생성  ⇄  ② 트리 검사      지어낸 기능 · 누락 · 모양
  │               문제가 있으면 피드백을 붙여 ①을 다시 (최대 2회)
  │ 통과
  ▼
③ TC 생성    ⇄  ④ TC 검사        규칙 → Judge, 지어낸 수치 · 분량 · TC 없는 AC
  │               문제 있는 TC만 ③을 다시 (최대 2회, 끝내 못 고치면 FAIL)
  ▼
리포트 (TC · 공백 · TC 없는 AC · 실행 흐름)
```

| 단계 | 하는 일 | 코드 | 프롬프트 |
|---|---|---|---|
| ① 트리 생성 | 기획서의 기능을 대/중/소분류 트리로 정리합니다. 노드마다 기획서 원문을 인용해 붙입니다 | `tree.py` | `tree.md` |
| ② 트리 검사 | **지어냄**: 인용한 문장이 기획서에 진짜 있는지 글자로 대조합니다(코드). **누락**: 어느 노드에도 안 걸린 기획서 문장을 코드가 골라내고, 그게 빠진 기능인지는 LLM이 판단합니다. **모양**: 깊이, 중복, 빈 이름을 봅니다(코드) | `tree_check.py` | `tree_check.md` |
| ③ TC 생성 | leaf마다 요구사항(AC)을 뽑고, TC 목록을 짠 다음, TC를 하나씩 씁니다. 동작이 안 적힌 leaf는 TC를 만들지 않고 공백으로 올립니다 | `tc.py` | `requirements.md`, `plan.md`, `write.md` |
| ④ TC 검사 | 규칙(형식, 분량, 디자인 수치, 원문에 없는 수치)을 먼저 보고, 통과하면 LLM Judge가 봅니다. 마지막에 어떤 TC도 다루지 않은 AC를 찾습니다 | `tc_check.py` | `judge.md` |

"만들고 → 검사하고 → 걸리면 피드백을 붙여 다시 만든다"는 루프는 `gate.py`에만 있고, 트리·AC·TC가 같은 루프를 씁니다. `pipeline.py`는 무엇을 만들고 무엇으로 검사할지만 이어 줍니다.

데이터는 위에서 아래로만 흐릅니다. 이름과 경로(`path`)는 트리의 leaf에서 TC까지 그대로 이어져서, 같은 기능의 TC가 서로 다른 분류로 갈라지지 않습니다.

```
기획서 텍스트 ─▶ FeatureNode (트리, id: F1, F1.2 …)
                    └▶ leaf마다 Requirement (acs, hints, priority)  또는  Gap (reason)
                          └▶ Outline (subject, scenario, covers)
                                └▶ TestCase (steps, expected, status: PASS/FAIL, notes)
```

## 사용법

외부 라이브러리 없이 돌아갑니다(Python 3.10 이상). LLM은 `complete(system, user) -> str` 메서드만 있으면 어떤 객체든 됩니다. 실제 모델 연결은 만들지 않았습니다(`tc_agent/llm.py`).

```python
from pathlib import Path

from tc_agent import pipeline, report
from tc_agent.llm import LLMClient


def make_report(llm: LLMClient) -> str:
    spec = Path("examples/sample_spec.md").read_text(encoding="utf-8")
    result = pipeline.run(spec, llm)
    return report.to_markdown(result)
```

이미 가지고 있는 분류 체계가 있으면 트리를 직접 넘길 수 있습니다. 이 경우 ①②는 건너뜁니다.

```python
from pathlib import Path

from tc_agent import pipeline, tree
from tc_agent.llm import LLMClient


def run_with_tree(llm: LLMClient):
    spec = Path("examples/sample_spec.md").read_text(encoding="utf-8")
    root = tree.parse_markdown_tree(Path("examples/sample_tree.md").read_text(encoding="utf-8"))
    return pipeline.run(spec, llm, tree=root)
```

## 실행 흐름 보기

각 단계는 무슨 일을 했는지 한 줄씩 남기고, 단계 이름은 위 흐름도의 ①~④를 그대로 씁니다.

```python
from tc_agent import pipeline, report
from tc_agent.llm import LLMClient


def show_flow(spec: str, llm: LLMClient) -> None:
    result = pipeline.run(spec, llm, on_event=print)   # 실행 중에 한 줄씩 출력
    print(report.to_flow_markdown(result))             # 단계별 요약표 + 일어난 순서대로의 기록
```

리포트(`to_markdown`)에는 단계별 요약표가, JSON(`to_json`의 `trace`)에는 기록 전체가 들어갑니다. ⚠가 붙은 줄은 사람이 한 번 봐야 하는 일입니다(근거가 없어 잘라낸 노드, 공백, 끝내 못 고친 FAIL, TC 없는 AC). 실제 모델 없이 출력 모양만 보고 싶으면 아래 데모를 돌리면 됩니다.

```bash
python3 examples/demo_flow.py     # 트리 누락이 잡혀 ①을 다시 하고, 규칙을 어긴 TC가 잡혀 ③을 다시 하는 흐름
```

```bash
python3 -m unittest discover -s tests
```

## 폴더

```
tc_agent/
├─ pipeline.py     전체 흐름: ①② stage_tree, ③④ stage_tc
├─ gate.py         만들기 → 검사 → 다시 만들기, 공통 루프
├─ tree.py         ① 트리 생성, 마크다운 트리 읽기
├─ tree_check.py   ② 트리 검사: 지어냄 · 누락 · 모양
├─ tc.py           ③ TC 생성: 요구사항(AC) → 계획 → 작성
├─ tc_check.py     ④ TC 검사: 규칙 + Judge, TC 없는 AC 찾기
├─ prompts/        단계별 프롬프트 (코드와 분리, 아래 참고)
├─ trace.py        단계별 실행 기록
├─ report.py       JSON / Markdown 출력
├─ models.py       데이터 모델
└─ llm.py          LLM 인터페이스, JSON 파서
examples/          예시 기획서·트리 (가상 문서), demo_flow.py
tests/             가짜 모델로 구조를 확인하는 테스트
docs/              DESIGN.md (설계), EVALUATION.md (평가 방법), ROADMAP.md (앞으로 할 일)
```

## 프롬프트 관리

프롬프트는 코드 밖 `tc_agent/prompts/*.md`에 있습니다. 문구를 고치려면 해당 `.md`만 수정하면 되고, 코드는 `prompts.TREE_SYSTEM` 같은 상수로 불러다 씁니다. 단계별 입출력 필드와 공통 원칙은 [tc_agent/prompts/README.md](tc_agent/prompts/README.md)에 정리했습니다. 프롬프트의 출력 형식(JSON 키)을 바꾸면 그 키를 읽는 단계 코드도 같이 바꿔야 합니다.

## 참고

- 실제 모델로 돌려 본 적이 없어서 품질 수치는 아직 없습니다.
- `examples/`의 문서는 예시로 만든 가상 문서입니다. 실제 기획서나 개인정보는 넣지 마세요.

---------------
## 작성시 AI를 활용한 영역
- 요구사항 및 구조 설계는 지원자인 제가 직접 했고, 코드 구현 및 md파일 작성은 LLM으로 진행.

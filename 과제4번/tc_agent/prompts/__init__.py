"""단계별 프롬프트. 프롬프트 본문은 이 폴더의 .md 파일에 있고, 여기서는 읽어서 상수로 내보낼 뿐이다.

    prompts.TREE_SYSTEM       <- tree.md           ① 트리 생성
    prompts.TREE_CHECK_SYSTEM <- tree_check.md     ② 트리 검사 (빠진 기능 판정)
    prompts.REQ_SYSTEM        <- requirements.md   ③ TC 생성 - leaf별 요구사항(AC)
    prompts.PLAN_SYSTEM       <- plan.md           ③ TC 생성 - 계획 (TC 목록)
    prompts.WRITE_SYSTEM      <- write.md          ③ TC 생성 - 작성 / 재작성
    prompts.JUDGE_SYSTEM      <- judge.md          ④ TC 검사 (LLM Judge)

파일 내용이 곧 프롬프트 전체다(앞뒤 가공 없음). 프롬프트를 고칠 때는 .md 만 바꾸면 되고 코드는 건드리지 않는다.
공통 작성 원칙은 README.md 에 있다.

모듈을 불러올 때 한 번 읽어서 상수에 담는다. 같은 단계는 같은 문자열 객체를 계속 쓰므로, 테스트 스텁이
`system is prompts.TREE_SYSTEM` 으로 어느 단계의 호출인지 구분할 수 있다.
"""
from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent


def load(name: str) -> str:
    """prompts/<name>.md 를 그대로 읽는다. 없거나 비어 있으면 어느 파일인지 알려 주며 멈춘다."""
    path = _DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"프롬프트 파일이 없음: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"프롬프트 파일이 비어 있음: {path}")
    return text


TREE_SYSTEM = load("tree")
TREE_CHECK_SYSTEM = load("tree_check")
REQ_SYSTEM = load("requirements")
PLAN_SYSTEM = load("plan")
WRITE_SYSTEM = load("write")
JUDGE_SYSTEM = load("judge")

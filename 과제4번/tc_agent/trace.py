"""실행 흐름 기록. 파이프라인이 지금 어느 단계에서 무엇을 했는지 한 줄씩 남긴다.

단계는 네 개이고, 흐름도(README)의 ①~④와 같다. 기록은 PipelineResult.trace 에 쌓이고,
report.to_flow_markdown 이 보여 준다. 실행 중에 보려면 on_event 로 콜백을 넘긴다.

    pipeline.run(spec, llm, on_event=print)      # 한 줄씩 바로 출력
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# (키, 표시 이름). 순서가 흐름도의 번호다.
STAGES: list[tuple[str, str]] = [
    ("tree_build", "① 트리 생성"),
    ("tree_check", "② 트리 검사"),
    ("tc_build", "③ TC 생성"),
    ("tc_check", "④ TC 검사"),
]
STAGE_LABEL = dict(STAGES)

INFO, WARN = "info", "warn"           # warn: 사람이 볼 만한 일 (잘라냄, 공백, FAIL 등)


@dataclass
class Event:
    stage: str                        # STAGES 의 키
    message: str
    level: str = INFO

    def __str__(self) -> str:
        mark = "⚠ " if self.level == WARN else ""
        return f"[{STAGE_LABEL[self.stage]}] {mark}{self.message}"


class Trace:
    def __init__(self, on_event: Callable[[Event], None] | None = None):
        self.events: list[Event] = []
        self._on_event = on_event

    def add(self, stage: str, message: str, level: str = INFO) -> None:
        if stage not in STAGE_LABEL:
            raise ValueError(f"알 수 없는 단계: {stage}")
        ev = Event(stage, message, level)
        self.events.append(ev)
        if self._on_event:
            self._on_event(ev)

    def logger(self, stage: str) -> Callable[..., None]:
        """Trace 를 모르는 모듈에 넘기는 `log(메시지)` 함수."""
        return lambda message, level=INFO: self.add(stage, message, level)

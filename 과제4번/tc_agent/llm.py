"""LLM 연결부.

파이프라인이 LLM 에 바라는 건 `complete(system, user) -> str` 하나뿐이다. 어떤 모델을 쓸지는 정하지 않았으니
이 시그니처를 가진 객체를 만들어 pipeline.run() 에 넘기면 된다.

  system: 프롬프트 문자열
  user  : JSON 문자열
  반환   : 모델이 낸 텍스트 그대로 (JSON 으로 바꾸는 건 parse_json 이 한다)
"""
from __future__ import annotations

import json
import re
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def parse_json(text: str):
    """응답에서 JSON 을 꺼낸다. 코드펜스나 앞뒤 설명이 붙어 있어도 첫 JSON 값만 읽는다.

    JSON 이 없거나 깨졌으면 ValueError.
    """
    cleaned = re.sub(r"```(?:json)?", "", text)
    start = next((i for i, c in enumerate(cleaned) if c in "{["), -1)
    if start < 0:
        raise ValueError("응답에 JSON 이 없음")
    try:
        value, _ = json.JSONDecoder().raw_decode(cleaned, start)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e
    return value

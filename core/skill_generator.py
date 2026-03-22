"""
Skill Generator — LLM이 SKILL.md + tool.py를 자동 생성하여 등록합니다.

허브에도 없는 스킬을 자율적으로 생성합니다:
  1. LLM에게 스킬 목적과 이름을 전달
  2. SKILL.md와 tool.py 코드를 생성
  3. ~/.openchiken/skills/<name>/에 저장
  4. 문법 검증 후 등록
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.provider import get_provider

logger = logging.getLogger(__name__)

_USER_SKILLS_DIR = Path.home() / ".openchiken" / "skills"


class GeneratedSkill(BaseModel):
    skill_md: str = Field(description="SKILL.md 파일 전체 내용 (YAML 프런트매터 + 지시 텍스트)")
    tool_py: str = Field(description="tool.py 파일 전체 내용 (LangChain @tool 함수 + get_tools())")


_GENERATOR_SYSTEM = """당신은 OpenChiken AI 비서용 스킬(플러그인)을 생성하는 전문 개발자입니다.

주어진 스킬 이름과 목적에 맞는 SKILL.md와 tool.py를 생성하세요.

## SKILL.md 형식
```
---
name: {skill_name}
description: 한 줄 설명
enabled: true
version: 1.0.0
---

## 도구 설명

도구 사용법과 지시사항...
```

## tool.py 형식
```python
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def tool_name(param: str) -> str:
    \"\"\"Tool description.
    Args:
        param: Parameter description
    \"\"\"
    # 구현...
    return "result"

def get_tools() -> list:
    return [tool_name]
```

## 규칙
- API 키가 필요 없는 공개 API를 사용하세요.
- urllib.request만 사용하세요 (requests 금지, 추가 의존성 최소화).
- 에러 처리를 반드시 포함하세요.
- 한국어 답변을 기본으로 하세요.
- get_tools() 함수를 반드시 마지막에 정의하세요.
- 모든 tool 함수에는 명확한 docstring이 있어야 합니다."""


def validate_tool_py(code: str) -> bool:
    """tool.py 코드의 Python 문법을 검증합니다."""
    try:
        ast.parse(code)
        return True
    except SyntaxError as e:
        logger.error("Generated tool.py has syntax error: %s", e)
        return False


async def generate_skill(name: str, purpose: str) -> Path:
    """LLM으로 스킬을 생성하고 로컬에 저장합니다.

    Args:
        name: 스킬 식별자 (snake_case)
        purpose: 스킬의 목적 설명

    Returns:
        설치된 스킬 디렉토리 경로.
    """
    llm = get_provider().get_model().with_structured_output(GeneratedSkill)

    prompt = (
        f"스킬 이름: {name}\n"
        f"목적: {purpose}\n\n"
        "위 스킬에 맞는 SKILL.md와 tool.py를 생성하세요."
    )

    result: GeneratedSkill = await llm.ainvoke([
        SystemMessage(content=_GENERATOR_SYSTEM),
        HumanMessage(content=prompt),
    ])

    if not validate_tool_py(result.tool_py):
        raise ValueError(f"생성된 tool.py에 문법 오류가 있습니다 (skill: {name})")

    dest = _USER_SKILLS_DIR / name
    dest.mkdir(parents=True, exist_ok=True)

    (dest / "SKILL.md").write_text(result.skill_md, encoding="utf-8")
    (dest / "tool.py").write_text(result.tool_py, encoding="utf-8")
    (dest / "__init__.py").touch()

    logger.info("Skill '%s' auto-generated and saved to %s", name, dest)
    return dest

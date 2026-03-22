"""
OpenChiken Skill Manifest Schema
──────────────────────────────────
SKILL.md / APP.md 프런트매터를 검증하는 Pydantic 모델.

SkillLoader가 raw dict 대신 이 모델로 파싱하여
필드 누락·타입 오류 시 ValidationError로 명확하게 실패합니다.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class SkillManifest(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    requires_google_auth: bool = False
    requires_env: list[str] = []
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = []

    @field_validator("enabled", "requires_google_auth", mode="before")
    @classmethod
    def coerce_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() not in {"false", "0", "no", ""}
        return bool(v)

    @field_validator("requires_env", "tags", mode="before")
    @classmethod
    def coerce_list(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []


class AppManifest(BaseModel):
    """APP.md 프런트매터를 검증하는 모델. SkillManifest의 슈퍼셋."""

    name: str
    type: str = "app"
    description: str = ""
    enabled: bool = True
    skills: list[str] = []
    schedule: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = []
    # 앱 실행 제어 필드
    trigger_keywords: list[str] = []   # 자동 트리거 키워드 (텔레그램 등 채널)
    output_channel: str = "telegram"   # 결과 전송 채널 (telegram | none)

    @field_validator("enabled", mode="before")
    @classmethod
    def coerce_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() not in {"false", "0", "no", ""}
        return bool(v)

    @field_validator("skills", "tags", "trigger_keywords", mode="before")
    @classmethod
    def coerce_list(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

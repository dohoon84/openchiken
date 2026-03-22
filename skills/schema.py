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

    @field_validator("enabled", mode="before")
    @classmethod
    def coerce_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() not in {"false", "0", "no", ""}
        return bool(v)

    @field_validator("skills", "tags", mode="before")
    @classmethod
    def coerce_list(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

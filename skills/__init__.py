"""
OpenChiken Skill System
───────────────────────
OpenClaw/AgentSkills 호환 SKILL.md 기반 동적 스킬 로더.

스킬 탐색 순서 (높은 우선순위 → 낮은 우선순위):
  1. <project>/skills/<name>/   — 내장 스킬
  2. ~/.openchiken/skills/<name>/ — 사용자가 설치한 외부 스킬

각 스킬 디렉토리는 다음 파일을 포함합니다:
  - SKILL.md  : YAML 프런트매터 + AI 지시 텍스트 (필수)
  - tool.py   : LangChain @tool 함수 + get_tools() 반환 (선택)
  - __init__.py

SKILL.md 프런트매터 지원 필드:
  name               : 스킬 식별자 (기본값: 디렉토리명)
  description        : 한 줄 설명
  enabled            : true / false (기본값: true)
  requires_google_auth: true이면 credentials.json 없을 때 스킵
  requires_env       : 콤마 구분 필수 환경변수 목록 (없으면 스킵)
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from skills.schema import AppManifest, SkillManifest

logger = logging.getLogger(__name__)

_BUNDLED_SKILLS_DIR = Path(__file__).parent
_USER_SKILLS_DIR = Path.home() / ".openchiken" / "skills"
_BUNDLED_APPS_DIR = Path(__file__).parent / "apps"
_USER_APPS_DIR = Path.home() / ".openchiken" / "apps"

_SKIP_DIRS = {"__pycache__", "apps"}


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    tools: list = field(default_factory=list)
    enabled: bool = True
    requires_google_auth: bool = False


@dataclass
class App:
    """스킬 묶음(앱). 자체도 상위 스킬로 취급됩니다."""

    name: str
    description: str
    instructions: str
    sub_skills: list[str] = field(default_factory=list)
    schedule: str = ""
    enabled: bool = True
    version: str = "1.0.0"


class SkillLoader:
    """SKILL.md 파일을 스캔하여 스킬과 LangChain 도구를 동적으로 로드합니다."""

    @staticmethod
    def _get_enabled_skill_names() -> set[str] | None:
        """ENABLED_SKILLS 환경변수에서 활성화할 스킬 이름 집합을 반환합니다.

        'all' 또는 미설정이면 None을 반환(모든 스킬 활성화).
        """
        raw = os.getenv("ENABLED_SKILLS", "all").strip().lower()
        if not raw or raw == "all":
            return None
        return {name.strip() for name in raw.split(",") if name.strip()}

    def load_all(self) -> list[Skill]:
        """내장 스킬과 사용자 스킬을 모두 로드하여 반환합니다."""
        enabled_names = self._get_enabled_skill_names()
        skills: list[Skill] = []
        seen: set[str] = set()

        for skills_root in (_BUNDLED_SKILLS_DIR, _USER_SKILLS_DIR):
            if not skills_root.exists():
                continue
            for skill_dir in sorted(skills_root.iterdir()):
                if not skill_dir.is_dir() or skill_dir.name in _SKIP_DIRS:
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue

                skill = self._load_skill(skill_dir)
                if skill is None:
                    continue

                if skill.name in seen:
                    logger.debug("Skill '%s' already loaded – skipping duplicate", skill.name)
                    continue

                if enabled_names is not None and skill.name not in enabled_names:
                    logger.debug("Skill '%s' skipped by ENABLED_SKILLS setting", skill.name)
                    continue

                seen.add(skill.name)
                skills.append(skill)
                logger.info("Skill loaded: %s (%d tools)", skill.name, len(skill.tools))

        return skills

    def get_all_tools(self) -> list:
        """모든 활성 스킬의 LangChain 도구 목록을 반환합니다."""
        tools: list = []
        for skill in self.load_all():
            tools.extend(skill.tools)
        return tools

    def build_skill_instructions(self) -> str:
        """모든 활성 스킬의 AI 지시 텍스트를 합쳐서 반환합니다."""
        parts: list[str] = []
        for skill in self.load_all():
            if skill.instructions:
                parts.append(skill.instructions.strip())
        return "\n\n---\n\n".join(parts)

    def skill_exists(self, name: str) -> bool:
        """로컬(내장 + 사용자)에 해당 이름의 스킬이 존재하는지 확인합니다."""
        for skills_root in (_BUNDLED_SKILLS_DIR, _USER_SKILLS_DIR):
            if not skills_root.exists():
                continue
            skill_dir = skills_root / name
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                return True
        return False

    def get_all_skill_names(self) -> set[str]:
        """로컬에 존재하는 모든 스킬 이름을 반환합니다."""
        names: set[str] = set()
        for skills_root in (_BUNDLED_SKILLS_DIR, _USER_SKILLS_DIR):
            if not skills_root.exists():
                continue
            for skill_dir in skills_root.iterdir():
                if not skill_dir.is_dir() or skill_dir.name in _SKIP_DIRS:
                    continue
                if (skill_dir / "SKILL.md").exists():
                    names.add(skill_dir.name)
        return names

    def load_apps(self) -> list[App]:
        """내장 앱과 사용자 앱(APP.md)을 로드합니다."""
        apps: list[App] = []
        seen: set[str] = set()

        for apps_root in (_BUNDLED_APPS_DIR, _USER_APPS_DIR):
            if not apps_root.exists():
                continue
            for app_dir in sorted(apps_root.iterdir()):
                if not app_dir.is_dir() or app_dir.name in {"__pycache__"}:
                    continue
                app_md = app_dir / "APP.md"
                if not app_md.exists():
                    continue
                app = self._load_app(app_dir)
                if app is None or app.name in seen:
                    continue
                seen.add(app.name)
                apps.append(app)
                logger.info("App loaded: %s (%d sub-skills)", app.name, len(app.sub_skills))

        return apps

    def _load_app(self, app_dir: Path) -> App | None:
        """APP.md를 파싱하여 App 객체를 생성합니다."""
        try:
            text = (app_dir / "APP.md").read_text(encoding="utf-8")
            frontmatter_dict, instructions = _parse_skill_md(text)
            frontmatter_dict.setdefault("name", app_dir.name)

            try:
                manifest = AppManifest(**frontmatter_dict)
            except ValidationError as exc:
                logger.error("App '%s' manifest 검증 실패: %s", app_dir.name, exc)
                return None

            if not manifest.enabled:
                return None

            return App(
                name=manifest.name,
                description=manifest.description,
                instructions=instructions,
                sub_skills=manifest.skills,
                schedule=manifest.schedule,
                enabled=manifest.enabled,
                version=manifest.version,
            )
        except Exception as exc:
            logger.error("Failed to load app from '%s': %s", app_dir, exc, exc_info=True)
            return None

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _load_skill(self, skill_dir: Path) -> Skill | None:
        try:
            text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            frontmatter_dict, instructions = _parse_skill_md(text)

            # 디렉토리명을 name 기본값으로 사용
            frontmatter_dict.setdefault("name", skill_dir.name)

            try:
                manifest = SkillManifest(**frontmatter_dict)
            except ValidationError as exc:
                logger.error(
                    "Skill '%s' manifest 검증 실패: %s", skill_dir.name, exc
                )
                return None

            if not manifest.enabled:
                logger.debug("Skill '%s' is disabled", manifest.name)
                return None

            if manifest.requires_google_auth and not _google_credentials_available():
                logger.warning(
                    "Skill '%s' skipped: requires_google_auth=true but credentials.json not found. "
                    "Run 'openchiken-setup' to configure Google integration.",
                    manifest.name,
                )
                return None

            missing = [e for e in manifest.requires_env if not os.getenv(e)]
            if missing:
                logger.warning(
                    "Skill '%s' skipped: missing env vars: %s", manifest.name, missing
                )
                return None

            tools: list = []
            tool_py = skill_dir / "tool.py"
            if tool_py.exists():
                tools = _load_tools_from_file(tool_py, skill_name=manifest.name)

            return Skill(
                name=manifest.name,
                description=manifest.description,
                instructions=instructions,
                tools=tools,
                enabled=manifest.enabled,
                requires_google_auth=manifest.requires_google_auth,
            )
        except Exception as exc:
            logger.error("Failed to load skill from '%s': %s", skill_dir, exc, exc_info=True)
            return None


# ── 모듈 수준 헬퍼 ─────────────────────────────────────────────────────────────


def _parse_skill_md(text: str) -> tuple[dict[str, str], str]:
    """SKILL.md를 프런트매터 dict와 지시 텍스트로 분리합니다."""
    if not text.lstrip().startswith("---"):
        return {}, text.strip()

    match = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text.strip()

    frontmatter_text, instructions = match.group(1), match.group(2).strip()
    frontmatter: dict[str, str] = {}
    for line in frontmatter_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()

    return frontmatter, instructions


def _google_credentials_available() -> bool:
    """credentials.json 또는 token.json이 접근 가능한지 확인합니다."""
    try:
        from config.settings import settings
        creds_path = settings.google_credentials_path
        token_path = settings.google_token_path
        if creds_path.exists() or token_path.exists():
            return True
    except Exception:
        pass

    # fallback: 프로젝트 루트 직접 확인
    project_root = Path(__file__).resolve().parent.parent
    return (
        (project_root / "credentials.json").exists()
        or (project_root / "token.json").exists()
    )


def _load_tools_from_file(tool_py: Path, skill_name: str) -> list:
    """tool.py를 동적으로 임포트하고 get_tools() 또는 get_{name}_tools()를 호출합니다."""
    try:
        spec = importlib.util.spec_from_file_location(
            f"openchiken.skills.{skill_name}.tool", tool_py
        )
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        # 1순위: get_tools()
        if hasattr(module, "get_tools"):
            return module.get_tools()

        # 2순위: get_{skill_name}_tools() (레거시 명명 규칙 호환)
        legacy_name = f"get_{skill_name}_tools"
        if hasattr(module, legacy_name):
            logger.debug(
                "Skill '%s': using legacy loader '%s()' — consider renaming to get_tools()",
                skill_name, legacy_name,
            )
            return getattr(module, legacy_name)()

        # 3순위: get_*_tools() 패턴 자동 탐색
        for attr_name in dir(module):
            if attr_name.startswith("get_") and attr_name.endswith("_tools"):
                fn = getattr(module, attr_name)
                if callable(fn):
                    logger.debug("Skill '%s': found loader '%s()'", skill_name, attr_name)
                    return fn()

        logger.warning(
            "tool.py in skill '%s' has no recognizable get_tools() function", skill_name
        )
        return []
    except Exception as exc:
        logger.error("Failed to load tools from '%s': %s", tool_py, exc, exc_info=True)
        return []


# ── 편의 싱글턴 ────────────────────────────────────────────────────────────────

_loader: SkillLoader | None = None


def get_skill_loader() -> SkillLoader:
    """애플리케이션 전체에서 공유하는 SkillLoader 인스턴스를 반환합니다."""
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader

"""
Skill Hub Client — GitHub 레포 기반 스킬 디스커버리 및 다운로드.

별도 GitHub 레포(openchiken/skill-hub)에서 스킬을 탐색하고
~/.openchiken/skills/<name>/ 에 설치합니다.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SKILL_HUB_REPO = "dohoon84/skill-hub"
SKILL_HUB_BRANCH = "develop"
_RAW_BASE = f"https://raw.githubusercontent.com/{SKILL_HUB_REPO}/{SKILL_HUB_BRANCH}"

_USER_SKILLS_DIR = Path.home() / ".openchiken" / "skills"
_USER_APPS_DIR = Path.home() / ".openchiken" / "apps"

_index_cache: dict[str, Any] | None = None
_INDEX_CACHE_TTL = 300  # 5분


def _fetch_url(url: str, timeout: int = 15) -> str:
    """URL에서 텍스트 콘텐츠를 가져옵니다."""
    req = urllib.request.Request(url, headers={"User-Agent": "OpenChiken-Hub/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def get_hub_index(force_refresh: bool = False) -> dict[str, Any]:
    """허브의 index.json을 가져와 캐시합니다."""
    global _index_cache
    if _index_cache is not None and not force_refresh:
        return _index_cache

    url = f"{_RAW_BASE}/index.json"
    try:
        data = json.loads(_fetch_url(url))
        _index_cache = data
        logger.info("Hub index loaded: %d skills, %d apps",
                     len(data.get("skills", [])), len(data.get("apps", [])))
        return data
    except Exception as e:
        logger.warning("Failed to fetch hub index: %s", e)
        return {"skills": [], "apps": []}


def list_hub_skills() -> list[dict[str, str]]:
    """허브에서 사용 가능한 스킬 목록을 반환합니다."""
    index = get_hub_index()
    return index.get("skills", [])


def list_hub_apps() -> list[dict[str, str]]:
    """허브에서 사용 가능한 앱 목록을 반환합니다."""
    index = get_hub_index()
    return index.get("apps", [])


def hub_skill_exists(name: str) -> bool:
    """허브에 해당 이름의 스킬이 존재하는지 확인합니다."""
    return any(s.get("name") == name for s in list_hub_skills())


def download_skill(name: str) -> Path:
    """허브에서 스킬을 다운로드하여 ~/.openchiken/skills/<name>/에 저장합니다.

    Returns:
        설치된 스킬 디렉토리 경로.
    """
    dest = _USER_SKILLS_DIR / name
    dest.mkdir(parents=True, exist_ok=True)

    for filename in ("SKILL.md", "tool.py"):
        url = f"{_RAW_BASE}/skills/{name}/{filename}"
        try:
            content = _fetch_url(url)
            (dest / filename).write_text(content, encoding="utf-8")
            logger.info("Downloaded %s/%s", name, filename)
        except Exception as e:
            if filename == "SKILL.md":
                raise RuntimeError(f"허브에서 {name}/SKILL.md를 찾을 수 없습니다: {e}") from e
            logger.debug("Optional file %s/%s not found: %s", name, filename, e)

    init_file = dest / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")

    logger.info("Skill '%s' installed to %s", name, dest)
    return dest


def download_app(name: str) -> Path:
    """허브에서 앱을 다운로드하여 ~/.openchiken/apps/<name>/에 저장합니다."""
    dest = _USER_APPS_DIR / name
    dest.mkdir(parents=True, exist_ok=True)

    url = f"{_RAW_BASE}/apps/{name}/APP.md"
    try:
        content = _fetch_url(url)
        (dest / "APP.md").write_text(content, encoding="utf-8")
        logger.info("App '%s' installed to %s", name, dest)
    except Exception as e:
        raise RuntimeError(f"허브에서 {name}/APP.md를 찾을 수 없습니다: {e}") from e

    return dest

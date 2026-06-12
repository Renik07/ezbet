from __future__ import annotations

import re
from pathlib import Path


def load_guide_topic_seed() -> list[dict[str, object]]:
    markdown_path = _find_topics_markdown()
    if markdown_path is None:
        return []

    topics: list[dict[str, object]] = []
    current_section = "Гайды"

    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped.removeprefix("## ").strip()
            continue

        match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if match is None:
            continue

        topic_number = int(match.group(1))
        title = match.group(2).strip()
        topics.append(
            {
                "topic_number": topic_number,
                "title": title,
                "section": current_section,
                "category": _category_from_section(current_section),
            }
        )

    return topics


def _find_topics_markdown() -> Path | None:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[1] / "docs" / "guide-topics-365.md",
        current.parents[3] / "docs" / "guide-topics-365.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _category_from_section(section: str) -> str:
    if section == "Футбол":
        return "Футбол"
    if section == "Баскетбол":
        return "Баскетбол"
    if section == "Хоккей":
        return "Хоккей"
    if section == "Теннис":
        return "Теннис"
    if section.startswith("MMA"):
        return "MMA"
    if section == "Киберспорт":
        return "Киберспорт"
    if section.startswith("Олимпийский"):
        return "Олимпиада"
    if section == "Автоспорт":
        return "Автоспорт"
    if section.startswith("Регби"):
        return "Другие виды"
    if section == "Спорт и здоровье":
        return "Здоровье"
    if section == "Деньги и спорт":
        return "Деньги"
    if section.startswith("Технологии"):
        return "Технологии"
    return "Спорт"

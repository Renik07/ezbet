from __future__ import annotations

import re
from pathlib import Path

WORLD_CUP_2026_TOPICS: tuple[str, ...] = (
    "Как делать ставки на ЧМ-2026: полный гид для новичка.",
    "Ставки на групповой этап чемпионата мира.",
    "Как анализировать матч ЧМ перед ставкой.",
    "Банкролл-менеджмент на чемпионате мира.",
    "Как читать коэффициенты на ЧМ-2026.",
    "Лайв-ставки на чемпионат мира.",
    "Ошибки новичков на ЧМ.",
    "Как выбрать букмекера для ставок на чемпионат мира.",
    "Формат ЧМ-2026 и его влияние на ставки.",
    "Чек-лист перед любой ставкой на матч чемпионата мира.",
    "Какие рынки ставок на ЧМ-2026 подходят новичкам.",
    "Как оценивать форму сборных перед матчами чемпионата мира.",
    "Травмы, дисквалификации и составы: что проверять перед ставкой на ЧМ.",
    "Как календарь и перелеты влияют на матчи ЧМ-2026.",
    "Ставки на плей-офф чемпионата мира: чем они отличаются от группы.",
    "Тоталы и форы на ЧМ-2026: простое объяснение.",
    "Как не переоценивать фаворитов на чемпионате мира.",
    "Статистика сборных на ЧМ: какие цифры действительно полезны.",
    "Как смотреть линию перед матчем ЧМ и не спешить со ставкой.",
    "Психология ставок на чемпионате мира: как не играть эмоциями.",
    "Ставки на победителя ЧМ-2026: как оценивать долгосрочные рынки.",
    "Как анализировать сборные-дебютанты на чемпионате мира.",
    "Почему ничьи на групповом этапе ЧМ требуют отдельного подхода.",
    "Ставки на индивидуальные тоталы сборных на ЧМ-2026.",
    "Как оценивать мотивацию команд в третьем туре группы.",
    "Что такое value betting на чемпионате мира простыми словами.",
    "Как не попасть в ловушку громкого имени сборной на ЧМ.",
    "Ставки на карточки и угловые на чемпионате мира.",
    "Как погода и стадион могут влиять на матчи ЧМ-2026.",
    "Как смотреть статистику личных встреч перед матчем сборных.",
    "Почему товарищеские матчи перед ЧМ нельзя переоценивать.",
    "Как оценивать глубину состава сборной на длинном турнире.",
    "Ставки на лучших бомбардиров ЧМ-2026: что важно учитывать.",
    "Как плей-офф меняет риск в ставках на чемпионат мира.",
    "Почему фавориты ЧМ часто начинают турнир осторожно.",
    "Как использовать новости о стартовом составе перед ставкой на ЧМ.",
    "Ставки на обе забьют на чемпионате мира: когда рынок опасен.",
    "Как читать движение линии на матч ЧМ-2026.",
    "Экспресс-ставки на чемпионат мира: риски и здравый подход.",
    "Как вести дневник ставок во время ЧМ-2026.",
)

WEB_SEARCH_DEFAULT_SECTIONS = {
    "Киберспорт",
    "Спорт и здоровье",
    "Деньги и спорт",
    "Деньги, бизнес и ставки в спорте",
    "Технологии, медиа и культура спорта",
    "Истории, рейтинги и спортивная память",
}

FACT_DEPENDENT_MARKERS = (
    "самые ",
    "лучшие ",
    "топ-",
    "топ ",
    "рекорд",
    "в истории",
    "всех времен",
    "xxi века",
    "за последние",
    "главные звезд",
    "перспективн",
    "в 2026 году",
    "в этом сезоне",
    "современн",
    "будущ",
    "постепенно",
    "быстро",
    "развивается",
    "набирает",
    "меняется",
    "меняют",
    "изменил",
    "изменила",
    "изменили",
    "стал ",
    "стала ",
    "стали ",
    "как устроен",
    "как устроена",
    "как работает",
    "правил",
    "регламент",
    "рейтинг",
    "квалификац",
    "драфт",
    "потолок зарплат",
    "фэйр-плей",
    "антидоп",
    "var",
    "hawk-eye",
    "судьи оценивают",
    "судейские",
    "аналитик",
    "технолог",
    "календар",
    "популяр",
    "конкурирует",
    "олимпи",
    "паралимп",
    "саудовск",
    "mls",
    "кхл",
    "ncaa",
    "ufc",
    "женск",
    "формулы-1",
    "formula e",
    "motogp",
    "nascar",
    "wrc",
    "indycar",
    "медальный зачет",
    "история ",
    "легенд",
    "эпох",
    "династи",
    "спортивным символом",
    "путь от",
    "финал",
    "камбэк",
    "дерби",
    "противостояни",
    "авари",
    "скандал",
    "апсет",
    "титул",
    "чемпион",
)

HEALTH_AND_SAFETY_MARKERS = (
    "здоров",
    "травм",
    "восстанов",
    "питани",
    "гидратац",
    "сколько воды",
    "нагрузк",
    "усталост",
    "выгорани",
    "сон ",
    "разминк",
    "растяжк",
    "перетренирован",
    "сотрясени",
    "физиотерап",
    "весогон",
    "нокдаун",
    "через боль",
    "мышц",
    "связок",
    "травматизм",
    "после болезни",
    "спортивные врачи",
)

BUSINESS_AND_MONEY_MARKERS = (
    "высокооплачиваем",
    "богат",
    "дорог",
    "стоимость",
    "контракт",
    "трансфер",
    "зарплат",
    "зарабатыва",
    "призов",
    "фан-баз",
    "спонсор",
    "бренд",
    "мерч",
    "телеправ",
    "трансляц",
    "рынок",
    "бизнес",
    "коммерческ",
    "инвестицион",
    "экономик",
    "миллиард",
    "финанс",
    "окупаемост",
    "монетизац",
    "реклам",
    "туризм",
)

BIOGRAPHY_MARKERS = (
    "лионель месси",
    "криштиану роналду",
    "гвардиола",
    "моуринью",
    "мбаппе",
    "холанд",
    "беллингем",
    "майкл джордан",
    "леброн джеймс",
    "стефен карри",
    "лука дончич",
    "никола йокич",
    "яннис адетокунбо",
    "уэйн гретцки",
    "александр овечкин",
    "роджер федерер",
    "рафаэль надаль",
    "новак джокович",
    "серена уильямс",
    "мухаммед али",
    "майк тайсон",
    "флойд мейвезер",
    "мэнни пакьяо",
    "конор макгрегор",
    "хабиб нурмагомедов",
    "джон джонс",
    "ронда раузи",
    "s1mple",
    "zywoo",
    "faker",
    "майкл фелпс",
    "усэйн болт",
    "симона байлз",
    "элиуд кипчоге",
    "льюис хэмилтон",
    "михаэль шумахер",
    "макс ферстаппен",
    "айртон сенна",
    "тайгер вудс",
)

MEDIUM_SEARCH_MARKERS = (
    "самые ",
    "лучшие ",
    "топ-",
    "топ ",
    "рекорд",
    "в истории",
    "всех времен",
    "xxi века",
    "за последние",
    "в 2026 году",
    "в этом сезоне",
    "перспективн",
    "будущ",
    "быстро",
    "развивается",
    "набирает",
)


def load_guide_topic_seed() -> list[dict[str, object]]:
    markdown_paths = _find_topics_markdowns()
    topics: list[dict[str, object]] = [
        {
            "topic_number": index,
            "title": title,
            "section": "ЧМ-2026",
            "category": "Беттинг",
            "requires_web_search": _requires_web_search(title, "ЧМ-2026"),
            "search_context_size": _search_context_size(title, "ЧМ-2026"),
        }
        for index, title in enumerate(WORLD_CUP_2026_TOPICS, start=1)
    ]

    if not markdown_paths:
        return topics

    for markdown_path in markdown_paths:
        topics.extend(_load_markdown_topics(markdown_path, offset=len(WORLD_CUP_2026_TOPICS)))

    return topics


def _load_markdown_topics(markdown_path: Path, *, offset: int) -> list[dict[str, object]]:
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
                "topic_number": topic_number + offset,
                "title": title,
                "section": current_section,
                "category": _category_from_section(current_section),
                "requires_web_search": _requires_web_search(title, current_section),
                "search_context_size": _search_context_size(title, current_section),
            }
        )

    return topics


def _find_topics_markdowns() -> list[Path]:
    current = Path(__file__).resolve()
    filenames = ("guide-topics-365.md", "guide-topics-extra-325.md")
    found: list[Path] = []
    for filename in filenames:
        for parent in current.parents:
            candidate = parent / "docs" / filename
            if candidate.exists():
                found.append(candidate)
                break
    return found


def _category_from_section(section: str) -> str:
    if section.startswith("Футбол"):
        return "Футбол"
    if section.startswith("Баскетбол"):
        return "Баскетбол"
    if section.startswith("Хоккей"):
        return "Хоккей"
    if section.startswith("Теннис"):
        return "Теннис"
    if section.startswith("MMA"):
        return "MMA"
    if section == "Киберспорт":
        return "Киберспорт"
    if section.startswith("Олимпийский"):
        return "Олимпиада"
    if section == "Автоспорт":
        return "Автоспорт"
    if section.startswith("Регби") or section.startswith("Другие"):
        return "Другие виды"
    if section == "Спорт и здоровье":
        return "Здоровье"
    if section.startswith("Деньги"):
        return "Деньги"
    if section.startswith("Технологии"):
        return "Технологии"
    if section.startswith("Истории"):
        return "Спорт"
    return "Спорт"


def _requires_web_search(title: str, section: str) -> bool:
    if section == "ЧМ-2026":
        return False

    normalized = f"{title} {section}".lower()
    if section in WEB_SEARCH_DEFAULT_SECTIONS:
        return True
    if any(marker in normalized for marker in FACT_DEPENDENT_MARKERS):
        return True
    if any(marker in normalized for marker in HEALTH_AND_SAFETY_MARKERS):
        return True
    if any(marker in normalized for marker in BUSINESS_AND_MONEY_MARKERS):
        return True
    if any(marker in normalized for marker in BIOGRAPHY_MARKERS):
        return True
    return False


def _search_context_size(title: str, section: str) -> str:
    if section == "ЧМ-2026":
        return "low"

    normalized = f"{title} {section}".lower()
    if section in WEB_SEARCH_DEFAULT_SECTIONS:
        return "medium"
    if any(marker in normalized for marker in MEDIUM_SEARCH_MARKERS):
        return "medium"
    if any(marker in normalized for marker in HEALTH_AND_SAFETY_MARKERS):
        return "medium"
    if any(marker in normalized for marker in BUSINESS_AND_MONEY_MARKERS):
        return "medium"
    return "low"

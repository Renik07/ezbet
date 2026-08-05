from __future__ import annotations

PROMOTIONAL_GIVEAWAY_MARKERS = (
    "розыгрыш",
    "разыгрыва",
    "конкурс",
    "лотере",
    "акция",
    "giveaway",
    "give-away",
)

PROMOTIONAL_CALL_TO_ACTION_MARKERS = (
    "подпиш",
    "участвуй",
    "участвуйте",
    "присоединяй",
    "присоединитесь",
    "вступай",
    "вступите",
    "зарегистрируй",
    "зарегистрируйтесь",
    "сделай репост",
    "сделайте репост",
    "поставь лайк",
    "поставьте лайк",
    "оставь комментар",
    "оставьте комментар",
    "перейди по ссылке",
    "перейдите по ссылке",
)

PROMOTIONAL_REWARD_MARKERS = (
    "выиграй",
    "выиграйте",
    "выиграть",
    "выигрыш",
    "приз",
    "подар",
    "получи",
    "получите",
    "забери",
    "заберите",
    "бесплатн",
    "набор мяч",
)


def detect_promotional_giveaway(*parts: str | None) -> str | None:
    text = " ".join(part.strip().lower().replace("ё", "е") for part in parts if part and part.strip())
    if not text:
        return None

    giveaway_marker = next((marker for marker in PROMOTIONAL_GIVEAWAY_MARKERS if marker in text), None)
    call_to_action = next((marker for marker in PROMOTIONAL_CALL_TO_ACTION_MARKERS if marker in text), None)
    reward_marker = next((marker for marker in PROMOTIONAL_REWARD_MARKERS if marker in text), None)

    if giveaway_marker and (call_to_action or reward_marker):
        return f"обнаружена промо-комбинация «{giveaway_marker}»"
    if call_to_action and reward_marker:
        return f"обнаружен призыв «{call_to_action}» с обещанием приза"
    return None

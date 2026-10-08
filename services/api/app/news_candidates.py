"""Cheap rejection rules before paid news processing."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import re


def news_rejection_reason(item):
    parsed = urlsplit(item.url or '')
    if (parsed.hostname or '').lower() in {'sports.ru', 'www.sports.ru'}:
        if re.match(r'^/(?:tags(?:/|$)|[^/]+/match(?:/|$))', parsed.path):
            return 'non_news_page'
    if item.published_at < datetime.now(timezone.utc) - timedelta(hours=24):
        return 'expired_news'
    return None

"""Stable presentation time; never replaces the stored publication timestamp."""
from datetime import timedelta
import zlib


def news_display_time(article_id, published_at):
    offset = 120 + zlib.crc32(str(article_id).encode('utf-8')) % (54 * 60)
    return published_at - timedelta(hours=1) + timedelta(seconds=offset)

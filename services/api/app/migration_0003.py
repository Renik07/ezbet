"""Restore historical news publication dates from the stored article creation time."""

STATEMENTS = (
    """
    UPDATE articles a SET published_at = a.created_at
    FROM news_items n
    WHERE n.id = a.news_item_id AND n.status = 'published'
      AND a.raw_item_id NOT LIKE 'guide-topic:%'
      AND a.published_at IS DISTINCT FROM a.created_at
    """,
    """
    UPDATE news_items n SET published_at = a.published_at
    FROM articles a
    WHERE a.news_item_id = n.id AND n.status = 'published'
      AND a.raw_item_id NOT LIKE 'guide-topic:%'
      AND n.published_at IS DISTINCT FROM a.published_at
    """,
)

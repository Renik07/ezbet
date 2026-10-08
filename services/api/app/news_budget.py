"""Durable rolling-hour allowance shared by every paid news stage."""
import logging

NEWS_HOURLY_LIMIT = 8
LOCK_KEY = 4815162352


def claim_news_stage(repository, raw_item_id: str, stage: str) -> bool:
    if stage not in {'enrichment', 'planner', 'editorial'}:
        raise ValueError('Unknown news budget stage')
    with repository.connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_KEY,))
        row = c.execute('''SELECT stages, claimed_at > NOW() - INTERVAL '1 hour'
            FROM news_ai_budget WHERE raw_item_id=%s''', (raw_item_id,)).fetchone()
        if row and row[1]:
            if stage in row[0]:
                return False
            c.execute('UPDATE news_ai_budget SET stages=array_append(stages,%s) WHERE raw_item_id=%s', (stage, raw_item_id))
            return True
        used = c.execute("SELECT count(*) FROM news_ai_budget WHERE claimed_at > NOW() - INTERVAL '1 hour'").fetchone()[0]
        if used >= NEWS_HOURLY_LIMIT:
            logging.getLogger('uvicorn.error').info('news_budget_exhausted stage=%s limit=%s', stage, NEWS_HOURLY_LIMIT)
            return False
        c.execute('''INSERT INTO news_ai_budget (raw_item_id,stages) VALUES (%s,ARRAY[%s]::TEXT[])
            ON CONFLICT (raw_item_id) DO UPDATE SET claimed_at=NOW(),stages=EXCLUDED.stages''', (raw_item_id, stage))
        return True

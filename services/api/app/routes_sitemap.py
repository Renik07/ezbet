"""Small public sitemap projections, never article bodies or administrative data."""
from fastapi import APIRouter, Path
from . import runtime

router = APIRouter()
SITEMAP_SIZE = 1000


@router.get('/api/v1/sitemap')
def sitemap_index():
    with runtime.repository.connect() as connection:
        rows = connection.execute('''
            SELECT (a.sitemap_id - 1) / %s AS part, MAX(a.updated_at)
            FROM articles a JOIN news_items n ON n.id = a.news_item_id
            WHERE n.visibility = 'public'
            GROUP BY part ORDER BY part
        ''', (SITEMAP_SIZE,)).fetchall()
    return {'items': [{'id': row[0], 'updatedAt': row[1].isoformat()} for row in rows]}


@router.get('/api/v1/sitemap/{part}')
def sitemap_part(part: int = Path(ge=0, le=2147483647)):
    with runtime.repository.connect() as connection:
        rows = connection.execute('''
            SELECT a.slug, a.updated_at FROM articles a
            JOIN news_items n ON n.id = a.news_item_id
            WHERE a.sitemap_id BETWEEN %s AND %s AND n.visibility = 'public'
            ORDER BY a.sitemap_id
        ''', (part * SITEMAP_SIZE + 1, (part + 1) * SITEMAP_SIZE)).fetchall()
    return {'items': [{'slug': row[0], 'updatedAt': row[1].isoformat()} for row in rows]}

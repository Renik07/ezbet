"""Exercise sitemap ranges at 200,000 real PostgreSQL rows in an isolated schema."""
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from services.api.app import migrations, routes_sitemap


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is not configured')
class SitemapScaleTests(unittest.TestCase):
    def test_two_hundred_thousand_articles_have_bounded_stable_ranges(self):
        url = os.environ['TEST_DATABASE_URL']
        schema = 'sitemap_test_' + uuid.uuid4().hex
        with psycopg.connect(url) as c:
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        private = make_conninfo(url, options='-c search_path=' + schema)
        try:
            with psycopg.connect(private) as c:
                migrations.migrate(c)
                c.execute("""INSERT INTO news_items (id,title,description,category,published_at,source)
                    SELECT 'news-'||i,'Title','Description','football',NOW(),'Source'
                    FROM generate_series(1,200000) AS i""")
                c.execute("""INSERT INTO articles (id,slug,news_item_id,raw_item_id,title,dek,body,category,source_title,published_at)
                    SELECT 'article-'||i,'slug-'||i,'news-'||i,'raw-'||i,'Title','Dek','Body','football','Source',NOW()
                    FROM generate_series(1,200000) AS i ORDER BY i""")
            repo = SimpleNamespace(connect=lambda: psycopg.connect(private))
            with patch.object(routes_sitemap.runtime, 'repository', repo):
                index = routes_sitemap.sitemap_index()['items']
                self.assertEqual([item['id'] for item in index], list(range(200)))
                part = routes_sitemap.sitemap_part(123)['items']
                self.assertEqual(len(part), 1000)
                self.assertEqual(part[0]['slug'], 'slug-123001')
                self.assertEqual(part[-1]['slug'], 'slug-124000')
                self.assertEqual(len(routes_sitemap.sitemap_part(199)['items']), 1000)
                self.assertEqual(routes_sitemap.sitemap_part(200)['items'], [])
                with psycopg.connect(private) as c:
                    c.execute("UPDATE news_items SET visibility='hidden' WHERE id='news-123001'")
                    c.execute("UPDATE articles SET published_at=NOW()+INTERVAL '1 day' WHERE id='article-123002'")
                remaining = routes_sitemap.sitemap_part(123)['items']
                self.assertEqual(len(remaining), 999)
                self.assertEqual(remaining, part[1:])
                self.assertEqual(len(routes_sitemap.sitemap_part(124)['items']), 1000)
        finally:
            with psycopg.connect(url) as c:
                c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

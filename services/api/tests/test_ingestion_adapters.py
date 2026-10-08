"""Small source fixtures exercise the adapter/filter/parser boundaries without network."""
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

from services.api.app import ingestion_feeds, ingestion_article_extraction
from services.api.app.ingestion import ingest_sources_with_results, extract_article_enrichment
from services.api.app.models import SourceItem


class IngestionAdapterTests(unittest.TestCase):
    def source(self):
        return SourceItem(key='fixture', title='Fixture', url='https://example.com/rss', category='football')

    def test_rss_collection_filters_old_items_and_preserves_content_url(self):
        now = datetime.now(timezone.utc)
        xml = '<rss><channel>'
        for title, date, url in [
            ('Спартак победил Зенит в матче чемпионата России', now, 'https://example.com/news?id=123&amp;utm_source=feed'),
            ('Зенит объявил состав на матч чемпионата России', now - timedelta(hours=2), 'https://example.com/old'),
        ]:
            xml += f'<item><title>{title}</title><description>Встреча завершилась со счетом 1:0. Команда набрала три очка в чемпионате.</description><link>{url}</link><pubDate>{format_datetime(date)}</pubDate><category>Футбол</category></item>'
        xml += '</channel></rss>'
        with patch.object(ingestion_feeds, '_fetch_remote_document', return_value=xml) as fetch:
            items, results = ingest_sources_with_results([self.source()])
        fetch.assert_called_once()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].dedupe_key, 'https://example.com/news?id=123')
        self.assertEqual(items[0].tags, ['Футбол'])
        self.assertEqual(results[0].filter_reasons['older_than_max_age'], 1)
        self.assertEqual(results[0].fetch_status, 'ok')

    def test_atom_adapter_preserves_link_summary_and_date(self):
        date = datetime.now(timezone.utc).isoformat()
        xml = f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
            <title>Спартак объявил состав на матч чемпионата России</title>
            <link href="https://example.com/atom-news"/><updated>{date}</updated>
            <summary>Команда представила стартовый состав на предстоящую встречу.</summary>
            </entry></feed>'''
        with patch.object(ingestion_feeds, '_fetch_remote_document', return_value=xml):
            items, results = ingest_sources_with_results([self.source()])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, 'https://example.com/atom-news')
        self.assertIn('стартовый состав', items[0].summary)
        self.assertEqual(results[0].parse_status, 'ok')

    def test_html_extraction_keeps_article_metadata_and_paragraphs(self):
        title = 'Спартак победил Зенит в чемпионате России'
        lead = 'Московская команда выиграла домашний матч со счетом 1:0.'
        paragraphs = ['Спартак победил Зенит в домашнем матче чемпионата России со счетом 1:0.',
                      'Единственный гол был забит во втором тайме встречи после точного удара нападающего.']
        html = f'''<html><head><meta property="og:title" content="{title}">
            <meta property="og:description" content="{lead}">
            <meta name="keywords" content="Спартак, Зенит"></head><body>
            <article class="article-content">{''.join('<p>'+p+'</p>' for p in paragraphs)}</article></body></html>'''
        with patch.object(ingestion_article_extraction, '_fetch_remote_document', return_value=html):
            article = extract_article_enrichment('https://example.com/news')
        self.assertEqual(article.title, title)
        self.assertEqual(article.lead, lead)
        for paragraph in paragraphs:
            self.assertIn(paragraph, article.full_text)
        self.assertIn('Спартак', article.tags)

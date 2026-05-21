# ezbet.ru

План запуска проекта `ezbet.ru` как медиа + витрины легальных букмекерских компаний. Первый рынок запуска - русскоязычный, но архитектуру стоит держать готовой к запуску отдельных market-specific инстансов.

## 1. Идея проекта

`ezbet.ru` состоит из трех основных контуров:

- Контентное ядро: новости спорта и беттинга, аналитика, статьи, прогнозы
- Коммерческий слой: рейтинги букмекеров, страницы букмекеров, реферальные ссылки
- AI-слой: мониторинг новостей, формирование контент-плана, генерация и обновление контента

Базовый принцип:

- AI делает рутинную и массовую работу
- Человек задает правила, проверяет качество и вмешивается в спорных случаях

## 2. Главная архитектурная идея

Проект не строится вокруг одного "супер-агента". Вместо этого используется набор узких AI-агентов внутри управляемого workflow.

Роли системы:

- `Collect` - собирает новые материалы из источников
- `Classify` - определяет тип, тему, важность и новизну
- `Plan` - формирует и обновляет контент-план
- `Write` - создает черновики материалов
- `Review` - проверяет стиль, фактуру и риски
- `Publish` - публикует или отправляет на ручную проверку

## 3. Рекомендованный стек

### Frontend

- `Next.js`
- `TypeScript`
- `App Router`

Почему:

- хорошо подходит для SEO-проектов
- удобно рендерить статьи, рейтинги, страницы букмекеров
- легко делать публичный сайт и админку в одной экосистеме

### Market / locale strategy

На текущем этапе мультиязычность лучше понимать не как одну общую редакцию на все языки, а как `per-market deployment`.

Практически это значит:

- у каждого рынка свой набор источников
- у каждого рынка свой основной язык контента
- интерфейс фронтенда должен поддерживать `i18n`
- у каждого деплоя полезно хранить `market` и `default_locale`
- перевод одного и того же русского потока на все языки не должен быть базовой стратегией

Пример:

- `RU` инстанс: русский интерфейс, русские RSS-источники, русский контент
- `EN/Africa` инстанс: английский интерфейс, свои источники, английский контент

То есть на старте это скорее задача:

- конфигурации фронтенда
- конфигурации окружения
- market-specific источников и контент-пайплайна

### Backend / AI

- `Python`
- `FastAPI`

Почему:

- удобно для scraping, ingestion, NLP и AI-интеграций
- проще строить пайплайны обработки и фоновые сервисы

### Workflow / orchestration

- `Temporal`

Почему:

- надежно управляет длинными фоновыми процессами
- подходит для сценариев: собрать -> дедуп -> оценить -> спланировать -> сгенерировать -> проверить -> опубликовать

### Scheduler

В проекте нужен scheduler, который по расписанию запускает регулярные процессы.

Что он делает:

- запускает проверку источников по фиксированным окнам времени
- запускает утреннюю сборку контент-плана
- инициирует генерацию черновиков и публикационные задачи

Базовый режим для MVP:

- `4` запуска ingestion в день, например `09:00`, `12:00`, `15:00`, `18:00`
- каждый следующий запуск забирает только новые материалы после предыдущего успешного прохода
- для этого по каждому источнику хранится watermark: `last_published_at` и `last_external_id`

Практический смысл:

- scheduler отвечает за момент запуска
- workflow отвечает за шаги, повторы, статусы и обработку ошибок

### Основная база данных

- `PostgreSQL`

Почему:

- основное хранилище бизнес-сущностей
- хорошо подходит для контента, админки, логов, версий и связей между сущностями

### Векторный поиск

- `pgvector` внутри `PostgreSQL`

Почему:

- на первом этапе не нужен отдельный vector database
- удобно делать similarity search и дедуп близких материалов

### Кэш и техническое состояние

- `Redis`

Почему:

- кэш
- блокировки
- короткоживущие технические состояния
- защита от повторной обработки одной и той же новости

### Файловое хранилище

- `S3-compatible storage`

Решение на текущий этап:

- используем `S3-compatible storage` уже на старте
- `CDN` пока не обязателен
- `CDN` закладываем в план как следующий шаг при росте трафика

### Контейнеризация

- `Docker`
- `docker-compose` для локальной разработки и простого server deploy на первом этапе

## 4. Как использовать RSS и AI

На 2026 год `RSS` использовать логично. Но не вместо AI, а как источник доставки данных.

Правильное разделение ролей:

- `RSS / Atom / news sitemap / sitemap / scraping / API` = сбор сигналов и первичных данных
- `deterministic extraction` = попытка достать `title`, `summary`, `published_at`, `canonical URL`, `lead`, `full_text`
- `AI` = анализ, приоритизация, редактура и только точечный fallback там, где обычный код не справился

Рекомендация:

- если у источника есть `RSS` или `Atom`, использовать их в первую очередь
- если есть `news sitemap` или обычный `sitemap`, использовать их до AI-поиска
- если нет, подключать `HTML scraping`, API, Telegram и другие каналы
- AI включать после ingestion-слоя
- `web_search` не использовать как основной discovery-движок для всего потока новостей

Для production-режима целевая UX-модель такая:

- админ добавляет не технический adapter, а просто сайт или раздел новостей
- система сама делает `source probe`
- система определяет, какие discovery- и enrichment-способы доступны для этого домена
- дальше scheduler использует лучший доступный путь автоматически

Важно:

- не заставлять администратора разбираться в `rss`, `sitemap`, `scraping`, `ai_research`
- ручной `source_type` допустим как MVP-режим, но не как целевая продуктовая модель

Практический ingestion-priority:

1. `RSS / Atom`
2. `news sitemap`
3. `sitemap`
4. `listing page scraping`
5. deterministic article extraction
6. `AI extraction fallback`
7. `AI + web_search` только для сложных страниц и редких проблемных кейсов

## 5. AI-агенты

### 5.1 Source Scout

Собирает новые материалы из:

- RSS / Atom
- news sitemap / sitemap
- открытых API
- HTML-страниц
- Telegram и других каналов, если это нужно на следующих этапах

Что обязательно уметь:

- хранить `last_seen` / watermark по каждому источнику
- забирать только новые элементы после последнего успешного прохода
- не тянуть повторно весь исторический хвост при каждом запуске
- поддерживать гибко настраиваемый список источников без правок кода
- не ходить в дорогой AI-поиск, если новость можно получить детерминированно

### 5.1.0 Source Capability Probe

Это слой автоопределения возможностей источника.

Что он делает при добавлении нового сайта:

- проверяет наличие `news sitemap`
- проверяет наличие `rss / atom`
- проверяет наличие обычного `sitemap`
- проверяет, можно ли получить кандидатов со страницы раздела через `listing scrape`
- проверяет, удается ли затем добрать `full_text` у sample-статей

Что должно сохраняться в БД:

- `supports_news_sitemap`
- `supports_rss`
- `supports_sitemap`
- `supports_listing_scrape`
- `supports_direct_article_extraction`
- `needs_ai_fallback_for_full_text`
- `preferred_discovery_adapter`
- `fallback_adapter_chain`

Принцип:

- админ добавляет URL сайта или раздела
- probe сам строит capability profile
- дальше scheduler и ingestion опираются на этот profile, а не на ручной выбор adapter'а

### 5.1.1 Extraction / Enrichment Layer

Это отдельный слой между source discovery и editorial.

Что он делает:

- скачивает HTML статьи по `url`
- пытается детерминированно извлечь `full_text`, `lead`, `tags`, `published_at`
- сохраняет в `raw_items` уже извлеченные данные, а не только короткий RSS summary
- передает в AI уже известный контекст: `url`, `title`, `summary`, HTML

Порядок работы:

1. сначала обычный parser / extractor
2. если `full_text` слабый или пустой, `AI extraction` по уже скачанному HTML без `web_search`
3. если HTML слабый, обрезанный или не содержит тело статьи, только тогда `AI + web_search`

Продуктовый приоритет для `full_text`:

- главное получить содержательный текст той же новости, даже если он взят не с исходного домена
- если оригинальная статья не читается, допустимо брать `full_text` с другого надежного источника по тому же инфоповоду
- для этого нужно сохранять provenance: откуда именно был взят итоговый `full_text`

Практический provenance для `full_text`:

- `source_url` хранит исходный URL новости из `rss / sitemap / scraping`
- `full_text_source_url` хранит URL страницы, откуда реально взят `full_text`
- `full_text_source_title` хранит источник, откуда реально взят `full_text`
- `extraction_mode` показывает путь: `direct_html`, `llm_*_html_extraction` или `llm_*_web_search_extraction`

Принцип:

- `AI search` это не основной способ поиска новостей
- `AI search` это rescue-layer для extraction и редких проблемных сайтов
- для `full_text` приоритет у полноты фактуры по тому же инфоповоду, а не у совпадения исходного домена

### 5.1.2 Discovery vs Enrichment

Это два разных контура, их нельзя смешивать в одну грубую цепочку.

`Discovery` отвечает за поиск candidate news items:

- `news sitemap`
- `rss / atom`
- `sitemap`
- `listing scrape`
- в конце, если нужно, `AI/web search`

`Enrichment` отвечает за заполнение полей уже найденной новости:

- `canonical_url`
- `published_at`
- `title`
- `summary`
- `lead`
- `full_text`
- `tags`

Правильный flow:

1. собрать candidates несколькими discovery-адаптерами
2. дедуплицировать candidates
3. для каждого item запустить enrichment pipeline
4. прекращать pipeline, как только обязательные поля заполнены

То есть не "одна и та же новость идет по всем source adapters подряд", а:

- discovery дает список новостей
- enrichment добирает недостающие поля у каждой новости до нужного quality threshold

### 5.2 Dedup / Canonicalizer

Определяет:

- это новая новость или обновление старой
- какие источники относятся к одному инфоповоду

### 5.3 Triage Agent

Проставляет:

- важность
- срочность
- категорию
- потенциальную ценность для трафика

### 5.4 Content Planner

Формирует контент-план:

- стартовый план на день
- динамическое обновление при появлении более важных новостей

### 5.5 Writer Agent

Генерирует:

- заголовок
- краткое описание
- структуру статьи
- полный текст черновика

На MVP можно включить AI в первую практическую точку:

- AI делает редакторскую правку и улучшение черновика перед публикацией
- человек при необходимости быстро просматривает итог

### 5.6 Editor / Fact-check Agent

Проверяет:

- соответствие исходным материалам
- фактические риски
- стилистику
- воду и повторения

### 5.6.1 Quality Gate

Это отдельный post-processing слой после writer/editor.

Что он должен проверять:

- не получился ли текст слишком шаблонным
- есть ли новая ценность сверх сырого RSS summary
- нет ли лишней воды и повторов
- не слишком ли текст похож на исходник

Важно:

- не делать ставку на ненадежные `AI detectors`
- ориентироваться не на "маскировку под человека", а на полезность, оригинальность и качество текста
- если quality gate не пройден, материал отправляется на `rewrite pass` или в fallback-режим

### 5.7 SEO Agent

Готовит:

- SEO title
- meta description
- schema.org-поля
- внутреннюю перелинковку

### 5.7.1 Similarity / Uniqueness Checks

Это не то же самое, что дедупликация на входе.

Задачи этого слоя:

- проверять, не слишком ли похож итоговый текст на source summary
- проверять, не публикуем ли мы две почти одинаковые статьи у себя
- защищать от внутренних дублей и слишком близкого пересказа источника

Это нужно в первую очередь для:

- качества контента
- чистоты индексации
- органического SEO

### 5.8 Compliance Agent

Следит за:

- тональностью
- дисклеймерами
- рисковыми формулировками
- коммерческой маркировкой

### 5.9 Publisher Agent

Отвечает за:

- публикационный статус
- выбор раздела
- дату публикации
- автоматическую или ручную публикацию

### 5.10 Image Agent

На будущих этапах для статьи желательно автоматически создавать хотя бы одну сгенерированную иллюстрацию.

Короткий flow:

- после подготовки финального текста система формирует image prompt
- image agent генерирует 1 lead image для статьи
- изображение сохраняется в `S3-compatible storage`
- статья получает `cover_image_url`
- позже эту раздачу можно ускорить через `CDN`

## 6. Prompt Management в админке

Это нужно делать сразу как часть системы.

Зачем:

- менять поведение агентов без деплоя
- версионировать промпты
- безопасно тестировать новые версии
- быстро откатываться

Что хранить:

- `agent_key`
- `system_prompt`
- `developer_prompt`
- `input_template`
- `output_schema_version`
- `model`
- `temperature` или reasoning settings
- `status`
- `version`
- `notes`
- `created_by`
- `approved_by`
- `created_at`

Что обязательно предусмотреть:

- versioning
- history
- rollback
- staging / draft режим
- логирование того, какой промпт участвовал в генерации

Каждый результат генерации должен сохранять:

- `prompt_version_id`
- `model`
- `agent_name`
- `input_payload`
- `output_payload`
- `generated_at`

## 7. Данные и хранилища

### PostgreSQL

Хранит основные бизнес-данные:

- статьи
- версии статей
- контент-план
- букмекеров
- страницы букмекеров
- рейтинги
- реферальные сущности
- редакторские статусы
- логи и аудит

### Redis

Хранит быстрые временные данные:

- кэш
- distributed locks
- краткоживущие флаги обработки
- rate limiting

### S3-compatible storage

Хранит файлы и крупные артефакты:

- картинки статей
- логотипы букмекеров
- скриншоты источников
- HTML / XML snapshots
- экспортные файлы

Практическая рекомендация по хранению source-артефактов:

- не хранить HTML всех статей бессрочно в `PostgreSQL`
- сохранять в БД извлеченные поля: `full_text`, `lead`, `tags`
- HTML держать как short-lived cache или как отладочный snapshot только для проблемных кейсов
- избегать повторного скачивания одной и той же статьи без необходимости

### CDN

Не входит в обязательный стартовый этап.

План:

- на первом этапе использовать `S3-compatible storage`
- при росте трафика подключить `CDN` поверх storage для ускорения раздачи файлов

## 8. Базовая схема сущностей

Минимальный набор таблиц:

- `sources`
- `source_capabilities`
- `raw_items`
- `canonical_events`
- `event_clusters`
- `content_plan_items`
- `articles`
- `article_versions`
- `editor_reviews`
- `bookmakers`
- `bookmaker_reviews`
- `bookmaker_offers`
- `referral_links`
- `prompt_configs`
- `prompt_versions`
- `generation_logs`
- `publication_jobs`
- `audit_logs`

## 9. Этапы разработки

### Этап 1. MVP ядра

Сделать:

- [x] публичный сайт
- [x] простой визуал главной страницы
- [x] админку
- [x] `articles` как отдельную публичную сущность
- [x] публикацию полного текста статьи
- [x] `article detail page` вида `/news/[slug]`
- [ ] ручное создание и редактирование статей
- [ ] страницы букмекеров
- [ ] рейтинг букмекеров
- [ ] базовую SEO-структуру

### MVP на текущий момент

Минимальный автоматический MVP, на котором стоит сфокусироваться сейчас:

- [x] простой визуал главной страницы
- [x] поиск новостей
- [x] сбор новостей
- [x] публикация новостей
- [x] минимальное участие AI в редактуре статьи перед публикацией
- [x] переход из карточки в полноценную страницу статьи

Упрощенный MVP flow:

1. scheduler запускает сбор новостей
2. ingestion-сервис по watermark забирает только новые материалы из `RSS / sitemap / scraping / API`
3. сырой поток сохраняется в `raw_items`
4. для каждой статьи deterministic extractor пытается достать `full_text` и метаданные страницы
5. если extractor не справился, включается `AI extraction fallback`; `web_search` разрешается только как запасной вариант
6. raw-записям назначаются dedupe key, category и базовая importance score
7. из `raw_items` формируются публикационные `news_items`
8. создается черновик статьи
9. AI делает первичную редактуру, чистит стиль и структуру
10. статья публикуется на сайте

Что уже заложено в стартовом каркасе репозитория:

- `apps/web` с главной страницей и страницей поиска новостей
- `services/api` с MVP API для выдачи новостей и демо-ingestion
- `services/api` с первым RSS-ingestion endpoint и списком стартовых источников
- `services/api` с source registry в БД и управлением источниками из админки
- `services/api` с `source_sync_state` и watermark-логикой по каждому источнику
- `services/api` с persistence-слоем на `PostgreSQL` для новостей
- `services/api` с ingestion-first flow и таблицей `raw_items`
- `services/api` с рабочим `rss` ingestion adapter и probe-проверкой источников
- `services/api` с детерминированной дедупликацией и базовой triage-классификацией
- `services/api` с `content_plan_items` и простым planner-слоем поверх triage
- `services/api` с prompt-driven editorial layer: `prompt_configs`, `draft_articles`, `editor_reviews`
- `services/api` с отдельной сущностью `articles` и article detail API
- `services/api` работает в ручном тестовом режиме: reset -> ingest -> planner -> editorial
- `docker-compose.yml` для локального запуска `web + api + postgres + redis`
- `apps/web/studio` для просмотра prompt configs, черновиков и review-результатов
- `apps/web/news/[slug]` для полноценной страницы статьи

Стартовые подтвержденные RSS-источники в проекте:

- `Sports.ru` — `https://www.sports.ru/rss/topnews.xml`
- `Спорт-Экспресс` — `https://www.sport-express.ru/services/materials/news/se/`

### Этап 2. Автосбор новостей

Сделать:

- [x] подключение стартовых RSS-источников
- [x] гибкую конфигурацию источников
- [x] `last_seen` / watermark логику по каждому источнику
- [x] хранение опубликованных новостей в `PostgreSQL`
- [x] хранение `raw_items`
- [x] дедупликацию
- [x] первичную классификацию и оценку важности

### Этап 3. AI-редакция

Сделать:

- [x] content planner
- [x] генерацию черновиков
- [x] редакторскую проверку
- [x] prompt management в админке
- [x] read-only studio для просмотра prompts, drafts и reviews
- [x] quality gate после writer/editor
- [x] rewrite pass для слабых или слишком шаблонных текстов
- [x] similarity check между draft и source summary
- [x] similarity check между опубликованными материалами

### Этап 3.5. Ingestion / Extraction v2

Это следующий рабочий блок перед полноценной автопубликацией. Его цель:

- довести ingestion до production-уровня
- перестать зависеть только от короткого RSS summary и дорогого AI-discovery
- унифицировать заполнение `raw_items` для разных типов источников
- сократить долю `template fallback` и дать AI больше исходных данных
- сделать deterministic-first pipeline, где AI включается только на узких местах
- уйти от ручного выбора adapter'а админом к auto-probe и capability-based orchestration

Порядок реализации:

1. Вынести ingestion в отдельные adapter'ы по `source_type`
2. Подключить `news sitemap` / `rss` / `sitemap` как discovery-слой первого приоритета
3. Подключить `scraping` для listing pages и источников без RSS
4. Добавить `source capability probe` и сохранять capability profile в БД
5. Перевести ingestion с ручного `source_type` на capability-based adapter selection
6. Добавить item-level enrichment pipeline для `full_text` и метаданных страницы
7. Добавить `AI extraction fallback` по уже скачанному HTML для страниц, где deterministic extractor не справился
8. Разрешать `AI + web_search` только если HTML слабый или article body не найден
9. Улучшить source-state: retries, last successful parse, error counters
10. Добавить scheduler с фиксированными окнами запуска и инкрементальным добором новостей
11. Пересобрать importance scoring и triage
12. Усилить dedup до near-duplicate detection на недавнем окне
13. Свести `template fallback` к аварийному контуру

Почему именно так:

- сначала нужно сделать дешевый и надежный ingestion для разных типов источников
- потом дать writer/editor больше исходных данных
- и только после этого усиливать scoring, dedup и качество публикации
- дорогой AI-поиск должен остаться редким fallback, а не основой архитектуры

Сделать:

- [x] рабочий `rss` adapter как базовый production-safe источник
- [x] `news sitemap` adapter как следующий приоритетный discovery-слой
- [x] базовый `sitemap` adapter первой версии для сайтов без нормального RSS
- [x] `scraping` adapter первой версии для источников без RSS
- [x] `ai_research` adapter первой версии через OpenAI `web_search` как временный fallback
- [ ] вывести `ai_research` из основного happy path ingestion
- [x] базовый `source capability probe` для auto-detection `rss / news sitemap / sitemap / scraping`
- [ ] таблица или сущность `source_capabilities`
- [ ] capability-based adapter selection вместо обязательного ручного `source_type`
- [x] единый нормализованный `RawItem` flow для `rss`, `scraping` и `ai_research`
- [x] хранение и использование полного текста страницы-источника поверх короткого RSS summary
- [x] отдельный enrichment-слой для `full_text`, `lead`, `tags`, если их удается извлечь
- [x] базовый `AI extraction fallback` для article pages, где deterministic extractor не вытягивает `full_text`
- [ ] усилить `web_search` fallback: несколько search-стратегий и разрешение брать `full_text` с любого надежного источника по тому же инфоповоду
- [ ] сначала пробовать AI extraction по уже скачанному HTML без `web_search`
- [ ] item-level enrichment pipeline: добирать только недостающие поля, а не перезапускать весь source flow
- [ ] ограничить `web_search` budget rules: только top-priority материалы и только после провала обычного extraction
- [x] усиленный `AI preflight fallback`: проверка нескольких sample-новостей и `ready_ai`, если хотя бы одна статья даёт пригодный `full_text`
- [ ] единая валидация источников в админке в зависимости от `source_type`
- [x] безопасная активация новых источников: только поддерживаемые adapter'ы могут уходить в `active`
- [x] generic sitemap больше не пускаем в автоматический active-flow: для auto-pipeline доверяем только `rss`, `news_sitemap`, `scraping`, `ai_research`
- [x] улучшенное состояние обхода источников: last successful fetch, last successful parse, error counters, retry policy
- [ ] scheduler с фиксированными окнами, например `09:00 / 12:00 / 15:00 / 18:00`
- [x] конфигурируемый ingest scheduler: `enabled`, `interval_minutes`, `last_run_at`, `next_run_at`
- [x] настраиваемый scheduler batch-size на источник
- [x] первый шаг к разделению быстрого ingest и enrichment: scheduler умеет запускаться без inline enrichment
- [x] отдельный ручной enrichment run для добора `full_text`, `lead`, `tags` по уже собранным `raw_items`
- [x] отдельный enrichment scheduler: свой `enabled`, `interval_minutes`, `batch_size`, `tick/run` и состояние последнего прогона
- [x] отдельный безопасный scheduler trigger endpoint / job runner для автосбора всех active-источников
- [x] кнопка и форма в `/admin` для ручной настройки интервала автозагрузки новостей
- [x] защита от двойного запуска scheduler: advisory lock / job lock и проверка `is_due`
- [x] scheduler должен брать только новые новости относительно `source_sync_state`, а не перечитывать весь часовой диапазон по wall-clock
- [x] post-enrichment duplicate recheck: после нормализации `title/summary/full_text` свежая новость еще раз проходит cross-source near-duplicate проверку
- [ ] вернуть shortlist для enrichment scheduler после этапа тестов: по `score / triage / freshness / duplicate-state`, без draft-элементов
- [x] editorial scheduler как отдельный автоматический этап после enrichment
- [ ] после этапа тестов вернуть более строгий shortlist для planner/editorial, чтобы в auto-pipeline не шли все `low` подряд
- [ ] publish scheduler / publish rules как отдельный этап после editorial
- [ ] вернуть rewrite-pass в editorial scheduler после этапа тестов; сейчас он временно отключен, чтобы не раздувать длительность одного прогона
- [x] базовая run history по pipeline-этапам: ingest / enrichment / editorial
- [ ] structured logging по этапам с `run_id`, `source`, `counts`, `duration`, `status`, `error_reason`
- [~] per-item diagnostics: базовый слой уже есть в `/studio` (duplicate, enrichment, content plan, editorial/publish state); дальше добавить причины именно непопадания в auto-publish rules
- [~] publish rules: базовые `publish_decision / publish_reason` уже есть в editorial-слое; дальше вынести их в отдельный publish scheduler и admin-control
- [x] publish rules + отдельный publish scheduler: editorial теперь только готовит `ready_for_publish`, а отдельный publish-этап публикует только `publish_auto`
- [x] базовый блок наблюдаемости в `/admin`: последние прогоны, counters, last successful run, ошибки по этапам
- [ ] ближайший приоритет: сначала observability и run history для всего pipeline, и только потом publish automation
- [x] importance scoring v2: лучше учитывать свежесть, источник, сущности и тип инфоповода
- [x] shortlist AI rerank только для верхних кандидатов, а не для всего потока
- [x] dedup v2: near-duplicate detection по недавнему окну, а не только по URL/title
- [x] свести `template fallback` к аварийному режиму, а не к обычному пути публикации

Что уже считаем честно рабочим:

- `rss` -> `raw_items` -> `planner` -> `editorial` -> `articles`
- watermark / `last_seen` логика по активным RSS-источникам
- ручной тестовый цикл через `/admin`
- `full_text` enrichment сразу после ingestion для источников, у которых доступна страница статьи
- AI fallback extraction для проблемных страниц статьи, если deterministic parser не справился с `full_text`

Что пока еще MVP-заглушка или упрощение:

- `scraping` и `ai_research` уже реализованы как adapters первой версии, но еще требуют site-specific tuning
- `news sitemap` уже добавлен, но capability-based orchestration еще не построен
- `sitemap` adapter уже есть в базовой версии, но его еще нужно прогнать на реальных сайтах и подкрутить эвристики
- базовый `source capability probe` уже есть, но capability profile пока хранится в `source_sync_state`, а не в отдельной сущности
- админка уже работает по сценарию `Проверить -> Добавить -> active`, но пока еще сохраняет явный `source_type`, а не полностью скрывает adapter-слой
- scheduler как реальный автозапуск по времени еще не доведен до production-режима
- текущий sync ingestion уже умеет сразу добирать `full_text`, но для production его нужно развести на быстрый ingest и отдельный background enrichment, чтобы длинние прогоны не падали по времени
- для production scheduler лучше делать не как вечный таймер внутри web API процесса, а как внешний cron / job trigger, который вызывает ingestion-runner по расписанию
- watermark-инвариант: запуск в `08:00` не должен повторно тянуть то, что уже было успешно обработано в `07:00`; ориентиром служит `last_published_at / last_external_id`, а не просто текущее время
- `full_text` и тяжелый enrichment не должны идти по всему потоку подряд; сначала нужен shortlist нужных новостей, и только потом дорогой добор контекста
- для production нужна не только консольная отладка, а полноценная observability-модель: structured logs, run history, item diagnostics и admin-панель состояния pipeline

Локальный dev-тест scheduler:

- включить scheduler и задать интервал в `/admin`
- разово дернуть scheduler: `npm run scheduler:tick`
- крутить локальный цикл, имитирующий внешний cron: `npm run scheduler:loop`
- при необходимости форсировать запуск в обход `is_due`: `SCHEDULER_MODE=run npm run scheduler:tick`
- при необходимости поменять API URL: `EZBET_API_BASE_URL=http://localhost:8000 npm run scheduler:tick`
- importance score пока rule-based и базовый
- planner пока детерминированный, а не AI-assisted
- RSS чаще всего дает краткий summary, а не полный текст статьи
- часть editorial flow все еще может уходить в `template fallback`

### Этап 4. Частичная автопубликация

Сделать:

- [ ] автоматическую публикацию низкорисковых форматов
- [ ] правила исключений для чувствительных публикаций
- [ ] аварийный стоп-контур вместо обязательной ручной модерации каждой новости

### Этап 5. Коммерческий слой

Сделать:

- [ ] развитые страницы букмекеров
- [ ] comparison pages
- [ ] реферальные блоки
- [ ] аналитика переходов и конверсий

### Этап 6. Масштабирование

Сделать:

- [ ] подключение CDN
- [ ] оптимизацию стоимости AI
- [ ] антидубль и антиспам-логику
- [ ] улучшение SEO и внутренней перелинковки
- [ ] генерацию хотя бы одной AI-иллюстрации для каждой статьи
- [ ] поддержку `market` / `default_locale` на уровне конфигурации инстанса
- [ ] frontend i18n для market-specific деплоев
- [ ] раздельные source registries и контентные пайплайны для разных рынков

## 10. Деплой и CI/CD

Нужно сразу строить удобную цепочку, чтобы проект можно было безопасно обновлять и масштабировать.

### Репозиторий

- `GitHub`

### Ветки

Рекомендуемая схема:

- `main` - production
- `develop` - интеграционная ветка, если команда будет активно работать параллельно
- feature branches для задач

Если команда маленькая, можно начать проще:

- `main`
- feature branches
- pull requests

### Docker

Каждый ключевой сервис упаковывается в контейнер:

- `web`
- `api`
- `worker`
- `scheduler`

Плюсы:

- одинаковое окружение локально и на сервере
- проще деплой
- проще масштабирование

### GitHub Actions

Использовать для CI:

- lint
- typecheck
- tests
- build
- сборка Docker images

Базовый pipeline:

1. push / pull request
2. запуск lint
3. запуск typecheck
4. запуск unit / integration tests
5. build приложений
6. build docker images
7. при merge в `main` - deploy

Что уже сделано в репозитории:

- добавлен базовый `CI` workflow в `.github/workflows/ci.yml`
- web-проект проверяется через lint и build
- API проходит установку пакета и compile-check

### Registry

Хранить Docker images в:

- `GitHub Container Registry`

### Deploy

Для первого этапа рекомендую простой и удобный вариант:

- один или два облачных сервера
- `Docker Compose` на сервере
- деплой через `GitHub Actions`

Пример production-цепочки:

1. разработчик пушит изменения в feature branch
2. создается pull request в `main`
3. `GitHub Actions` гоняет проверки
4. после merge в `main` собираются production Docker images
5. образы пушатся в `GitHub Container Registry`
6. workflow по SSH подключается к серверу
7. сервер делает `docker compose pull`
8. сервер делает `docker compose up -d`
9. выполняются миграции базы
10. healthcheck подтверждает, что сервисы поднялись

### Что будет крутиться на сервере

- `nginx` или другой reverse proxy
- `web`
- `api`
- `worker`
- `scheduler`
- `postgres`
- `redis`

Позже можно вынести `Postgres` и storage в managed services.

### Почему такой деплой хорош для старта

- недорого
- прозрачно
- легко отлаживать
- не требует раннего перехода в Kubernetes

### Что добавить позже

- staging environment
- blue/green или rolling deploy
- managed PostgreSQL
- managed Redis
- CDN
- отдельный monitoring stack

## 11. Предлагаемая структура репозитория

```text
ezbet/
  apps/
    web/
    admin/
  services/
    api/
    ai/
  workers/
    temporal/
  packages/
    ui/
    config/
    types/
  infra/
    docker/
    nginx/
    github-actions/
  docs/
```

## 12. Быстрый старт локально

Когда зависимости будут установлены, локальный запуск MVP должен выглядеть так:

```bash
npm run dev
```

Что поднимется:

- `web` на `http://localhost:3000`
- `api` на `http://localhost:8000`
- `postgres` на `localhost:5433`
- `redis` на `localhost:6379`

Чтобы включить живую генерацию через LLM API:

- скопировать `.env.example` в `.env`
- задать `OPENAI_API_KEY`
- при необходимости задать `OPENAI_MODEL` как общий fallback
- при необходимости задать `OPENAI_EDITORIAL_MODEL` и `OPENAI_SEARCH_MODEL` отдельно
- при необходимости задать `OPENAI_BASE_URL`, `OPENAI_API_STYLE` и `OPENAI_PROVIDER_LABEL`
- при необходимости включить `OPENAI_WEB_SEARCH_ENABLED=true`
- `web_search` имеет смысл держать выключенным по умолчанию и включать только для точечного extraction fallback
- для discovery новостей не стоит строить основную архитектуру вокруг `web_search`
- если ключ не задан или API недоступен, система падает обратно в template fallback
- стартовый шаблон переменных лежит в `.env.example`

Пример для `OpenAI`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini
OPENAI_EDITORIAL_MODEL=gpt-5-mini
OPENAI_SEARCH_MODEL=gpt-5-mini
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_STYLE=responses
OPENAI_PROVIDER_LABEL=OpenAI
OPENAI_WEB_SEARCH_ENABLED=true
OPENAI_WEB_SEARCH_LIVE=true
OPENAI_WEB_SEARCH_CONTEXT_SIZE=medium
```

Пример для `DeepSeek`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=deepseek-v4-flash
OPENAI_EDITORIAL_MODEL=deepseek-v4-flash
OPENAI_SEARCH_MODEL=deepseek-v4-flash
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_STYLE=chat_completions
OPENAI_PROVIDER_LABEL=DeepSeek
```

Отдельные команды:

```bash
npm run dev:infra
npm run dev:api
npm run dev:web
```

Полезные endpoints:

- `GET /health`
- `GET /api/v1/news`
- `GET /api/v1/raw-items`
- `GET /api/v1/drafts`
- `GET /api/v1/prompts`
- `GET /api/v1/reviews`
- `GET /api/v1/content-plan`
- `GET /api/v1/source-states`
- `GET /api/v1/sources`
- `POST /api/v1/prompts`
- `POST /api/v1/prompts/{prompt_id}/status`
- `POST /api/v1/ingest/demo`
- `POST /api/v1/ingest/sources`
- `POST /api/v1/dev/reset`

Практический smoke test перед `Этапом 4`:

1. В `/admin` нажать `Очистить БД`
2. Нажать `Загрузить 5 новостей`
3. Нажать `Обновить content plan`
4. Нажать `Запустить editorial run`
5. Проверить:
   - `/studio` показывает пары `RAW RSS -> AI DRAFT`
   - `/` показывает только AI-обработанные новости
- `POST /api/v1/ingest/sources`
- `POST /api/v1/content-plan/run`
- `POST /api/v1/editorial/run`

## 13. Ключевые принципы

- не строить все вокруг одного большого AI-агента
- не давать AI прямую бесконтрольную публикацию
- все важные AI-решения логировать
- все промпты версионировать
- сначала простая и надежная инфраструктура, потом усложнение
- `S3` использовать сразу
- `CDN` планировать как следующий шаг, а не как обязательную часть MVP
- не строить SEO вокруг `AI detector`, а строить вокруг полезности, оригинальности и качества
- различать `deduplication` на входе и `similarity/originality checks` на выходе
## 14. Ближайшие следующие шаги

1. Утвердить этот план как базовый архитектурный документ
2. Доделать `sitemap` adapter
3. Добавить `source capability probe` и хранение capability profile
4. Перевести админку с ручного выбора adapter'а на сценарий "добавить сайт"
5. Собрать capability-based discovery pipeline
6. Добавить item-level enrichment pipeline до заполнения обязательных полей
7. Развести production pipeline на быстрый ingest и отдельный background enrichment, чтобы длинняя загрузка новостей не падала
8. Усилить `web_search` fallback для `full_text`: искать по `title + summary` и разрешать брать текст с любого надежного источника того же инфоповода
9. Настроить scheduler и провести первый сквозной тест: добавить сайт -> забрать новости -> добрать `full_text` -> опубликовать

# Источники
1. https://www.sport-express.ru/services/materials/news/se - RSS (Сбор новостей  - ОК. ФУЛЛ текст берется через веб-поиск)
2. https://www.championat.com/sitemap/news.xml - news sitemap (Сбор новостей - ОК. ФУлл текст - Через скрапинг/парсинг OK)
3. https://www.sports.ru (https://www.sports.ru/news) - scraping (Сбор новостей - ОК. ФУлл текст - Через скрапинг/парсинг OK)
4. https://www.sovsport.ru (https://www.sovsport.ru/sitemap-news.xml) - news sitemap (Сбор новостей - ОК. ФУлл текст - Через скрапинг/парсинг OK)
5. https://www.sportsdaily.ru/news/ - scraping (Сбор новостей - ОК. ФУЛЛ текст берется через веб-поиск)

# Убить процесс
1. lsof -i :8000
2. kill -9 <PID>

# Commands
npm run dev:infra

npm run dev:api
npm run dev:web
npm run scheduler:tick (npm run scheduler:loop)

"""Repository facade; persistence implementations are grouped by domain."""
from .repository_database import DatabaseRepository
from .repository_forecasts import ForecastsRepository
from .repository_sources import SourcesRepository
from .repository_schedulers import SchedulersRepository
from .repository_prompts import PromptsRepository
from .repository_guides import GuidesRepository
from .repository_raw_items import RawItemsRepository
from .repository_editorial import EditorialRepository
from .repository_publication import PublicationRepository
from .repository_mapping import MappingRepository
from .repository_support import InsertRawItemsResult, PrefilterRawItemsResult


class NewsRepository(
    DatabaseRepository,
    ForecastsRepository,
    SourcesRepository,
    SchedulersRepository,
    PromptsRepository,
    GuidesRepository,
    RawItemsRepository,
    EditorialRepository,
    PublicationRepository,
    MappingRepository,
):
    """Shared connection pool and transactional domain operations."""

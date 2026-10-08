"""Compatible AI client facade; transport and operation implementations are separate."""
from .ai_transport import TransportAIClient
from .ai_editorial import EditorialAIClient
from .ai_forecasts import ForecastsAIClient
from .ai_guides import GuidesAIClient
from .ai_sources import SourcesAIClient
from .ai_types import (
    DraftGenerationResult,
    GuideResearchResult,
    ReviewGenerationResult,
    PlannerRerankItem,
    SourceDiscoveryItem,
    ResolvedArticleTarget,
    ArticleExtractionResult,
)


class OpenAIEditorialClient(
    TransportAIClient,
    EditorialAIClient,
    ForecastsAIClient,
    GuidesAIClient,
    SourcesAIClient,
):
    """Shared settings and transport for existing editorial operations."""

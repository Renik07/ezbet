"""HTTP application assembly; domain services and pipeline stages live separately."""
from fastapi import Depends, FastAPI

from .auth import authorize_api_route
from .bootstrap import lifespan
from .routes_monitoring import router as monitoring_router
from .routes_editorial import router as editorial_router
from .routes_news import router as news_router
from .routes_forecasts import router as forecasts_router
from .routes_sources import router as sources_router
from .routes_pipeline import router as pipeline_router

from .routes_sitemap import router as sitemap_router

app = FastAPI(
    title="ezbet API",
    version="0.1.0",
    description="MVP API for news collection, search, and publication.",
    lifespan=lifespan,
    dependencies=[Depends(authorize_api_route)],
)

app.include_router(monitoring_router)
app.include_router(editorial_router)
app.include_router(news_router)
app.include_router(forecasts_router)
app.include_router(sources_router)
app.include_router(pipeline_router)

app.include_router(sitemap_router)

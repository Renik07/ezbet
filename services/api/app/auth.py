"""Fail-closed authorization for non-public API routes."""
import os
from secrets import compare_digest

from fastapi import HTTPException, Request


PUBLIC_READ_ROUTES = frozenset({
    '/api/v1/sitemap', '/api/v1/sitemap/{part}',
    '/health', '/api/v1/news', '/api/v1/articles/{slug}',
    '/api/v1/forecasts', '/api/v1/forecasts/{slug}',
})


def admin_api_token() -> str:
    token = (os.getenv('EZBET_ADMIN_API_TOKEN') or '').strip()
    return '' if token in {'***', 'your_admin_api_token_here'} else token


def validate_admin_configuration() -> None:
    if (os.getenv('EZBET_ENV') or 'development').strip().lower() in {'production', 'prod'}:
        if len(admin_api_token()) < 32:
            raise RuntimeError('Production requires EZBET_ADMIN_API_TOKEN with at least 32 characters.')


def require_admin_api_token(request: Request) -> None:
    expected = admin_api_token()
    if not expected:
        raise HTTPException(status_code=503, detail='Admin API token is not configured.')
    provided = (request.headers.get('x-admin-token') or '').strip()
    if not compare_digest(provided.encode('utf-8'), expected.encode('utf-8')):
        raise HTTPException(status_code=403, detail='Admin token is required for this action.')


def authorize_api_route(request: Request) -> None:
    route = request.scope.get('route')
    if request.method in {'GET', 'HEAD'} and getattr(route, 'path', None) in PUBLIC_READ_ROUTES:
        return
    require_admin_api_token(request)

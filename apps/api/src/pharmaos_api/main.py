"""Application factory.

- Unified ApiResponse envelope for success and errors (CLAUDE.md).
- No stack traces or sensitive data ever reach the client (forbidden action #6).
- The local API binds to 127.0.0.1 only (see run()).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pharmaos_api.errors import ApiError, ErrorCode, error_envelope, success_envelope
from pharmaos_api.middleware import LoginRateLimitMiddleware, SecurityHeadersMiddleware
from pharmaos_api.routers import auth, pos, users

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="PharmaOS API", version="1.1.0", docs_url=None, redoc_url=None)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(LoginRateLimitMiddleware)

    app.include_router(auth.router)
    app.include_router(pos.router)
    app.include_router(users.router)

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=error_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Field locations only — never echo submitted values back.
        details = [
            {"loc": [str(part) for part in err.get("loc", [])], "type": err.get("type", "")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_envelope(ErrorCode.VALIDATION_FAILED, "Validation failed.", details),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        # Real error goes to the log ONLY (forbidden action #6: no stack traces to clients).
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_envelope("E-SYS-001", "Unexpected error."),
        )

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return success_envelope({"status": "ok"})

    return app


app = create_app()


def run() -> None:
    """Entry point — binds to 127.0.0.1 only (CLAUDE.md local security rule)."""
    import uvicorn

    from pharmaos_api.config import get_settings

    s = get_settings()
    uvicorn.run("pharmaos_api.main:app", host=s.api_host, port=s.api_port)

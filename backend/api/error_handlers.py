"""Global exception handlers — structured JSON for FYP / production clients."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.errors import RezumeAPIError

_log = logging.getLogger("rezume.api")


def _body(success: bool, error: str | None, code: str, extra: dict[str, Any] | None = None) -> dict:
    out: dict[str, Any] = {"success": success, "error": error, "code": code}
    if extra:
        out["detail"] = extra
    return out


async def rezume_api_error_handler(request: Request, exc: RezumeAPIError) -> JSONResponse:
    _log.warning("RezumeAPIError %s: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=_body(False, exc.message, exc.code),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, list):
        msg = "; ".join(str(d) for d in detail)
    else:
        msg = str(detail)
    code = f"HTTP_{exc.status_code}"
    return JSONResponse(
        status_code=exc.status_code,
        content=_body(False, msg, code),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errs = exc.errors()
    msg = errs[0].get("msg", "validation error") if errs else "validation error"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_body(False, msg, "VALIDATION_ERROR", extra={"errors": errs}),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_body(False, "Internal server error", "INTERNAL_ERROR"),
    )

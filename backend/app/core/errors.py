"""Map domain and validation failures without leaking submitted secrets."""
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Carry a safe status and message across service boundaries."""
    def __init__(self, status: int, message: str) -> None:
        """Initialize a safe client error.

        Args:
            status: HTTP failure status.
            message: Credential-free explanation.
        """
        super().__init__(message)
        self.status = status
        self.message = message


def register_errors(app: FastAPI) -> None:
    """Register safe failure responses at HTTP trust boundaries."""
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        """Return a domain failure with a bearer challenge for authentication."""
        return JSONResponse({"detail": exc.message}, status_code=exc.status,
                            headers={"WWW-Authenticate": "Bearer"} if exc.status == 401 else None)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Exclude raw input and validator context from validation output."""
        errors = [{"loc": list(error["loc"]), "type": error["type"], "msg": "Invalid value"} for error in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, exc: PyMongoError) -> JSONResponse:
        """Map conflicts separately and hide database diagnostics."""
        if isinstance(exc, DuplicateKeyError):
            return JSONResponse({"detail": "Record already exists"}, status_code=409)
        logger.error("Database operation failed (%s)", type(exc).__name__)
        return JSONResponse({"detail": "Service temporarily unavailable"}, status_code=503)

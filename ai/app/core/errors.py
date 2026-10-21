from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorDetail, ErrorResponse

HTTP_ERRORS: dict[int, tuple[str, str]] = {
    404: ("NOT_FOUND", "요청한 리소스를 찾을 수 없습니다."),
    405: ("METHOD_NOT_ALLOWED", "허용되지 않는 요청 방식입니다."),
}


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(by_alias=True, exclude_none=True),
        headers=headers,
    )


async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        ErrorDetail(field=_field_name(err["loc"]), reason=err["msg"]) for err in exc.errors()
    ]
    return error_response(400, "VALIDATION_FAILED", "입력값이 올바르지 않습니다.", details)


async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = HTTP_ERRORS.get(
        exc.status_code, (HTTPStatus(exc.status_code).name, str(exc.detail))
    )
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    return error_response(500, "INTERNAL_ERROR", "서버에서 예기치 않은 오류가 발생했습니다.")


def _field_name(loc: tuple[int | str, ...]) -> str:
    parts = loc[1:] if len(loc) > 1 else loc
    return ".".join(str(p) for p in parts)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

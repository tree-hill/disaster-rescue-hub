from __future__ import annotations


class BusinessError(Exception):
    """所有业务错误的基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        details: list[dict] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or []
        super().__init__(message)

"""Error types shared by every layer (foundation: leaf module)."""

from __future__ import annotations

# Problem details (API.md, api/1): the one error shape that
# crosses the seam. Titles are constant per type; clients
# switch on the type URI, never on the title or the detail.
PROBLEM_TITLES = {
    "not-found": "Not Found",
    "validation": "Validation Failed",
    "conflict": "Conflict",
    "internal": "Internal Error",
}


def problem_details(
    code: str,
    status: int,
    detail: str,
    correlation_id: str,
    field_errors: list[dict] | None = None,
) -> dict:
    """Build one problem-details payload for the API seam."""
    problem = {
        "type": f"urn:problem:{code}",
        "title": PROBLEM_TITLES.get(code, "Error"),
        "status": status,
        "detail": detail,
        "correlation_id": correlation_id,
    }
    if field_errors is not None:
        problem["field_errors"] = field_errors
    return problem


class AppError(Exception):
    """Base error carrying a machine code for the API seam."""

    code = "internal"
    status = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(AppError):
    code = "not-found"
    status = 404


class Validation(AppError):
    code = "validation"
    status = 422

    def __init__(self, message: str, field_errors: list[dict]) -> None:
        super().__init__(message)
        self.field_errors = field_errors


class Conflict(AppError):
    code = "conflict"
    status = 409

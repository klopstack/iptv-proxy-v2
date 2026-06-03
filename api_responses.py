"""
Standardized API success response helpers (TODO 73).

Collection/resource reads use ``{ "data": ... }``.
Mutations use ``{ "success": true, "data": ... }`` (optional ``message``).
Deletes return 204 No Content.
"""

from flask import jsonify

ERROR_CODES = {
    400: "BAD_REQUEST",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def default_error_code(status_code):
    """Map HTTP status to symbolic error code."""
    return ERROR_CODES.get(status_code, "ERROR")


def data_response(data, status_code=200):
    """Wrap a collection or resource read in ``{ "data": ... }``."""
    return jsonify({"data": data}), status_code


def success_response(data=None, *, status_code=200, message=None):
    """Return a mutation success envelope."""
    body = {"success": True}
    if data is not None:
        body["data"] = data
    if message is not None:
        body["message"] = message
    return jsonify(body), status_code


def no_content():
    """Return 204 No Content for successful deletes."""
    return "", 204

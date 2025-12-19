"""
Standardized error handling for the application

Provides:
- Consistent error response format
- Error handler decorators
- Flask error handlers for common HTTP errors
- Safe error logging (never exposes internal details to users)
"""
import logging
import traceback
from functools import wraps

from flask import Response, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


# ============================================================================
# Error Response Format
# ============================================================================


def error_response(message, status_code=400, details=None):
    """
    Create a standardized error response

    Args:
        message: User-friendly error message
        status_code: HTTP status code
        details: Optional additional details (dict)

    Returns:
        tuple: (response, status_code)
    """
    response = {"success": False, "error": message}

    if details:
        response["details"] = details

    return jsonify(response), status_code


def text_error_response(message, status_code=400):
    """
    Create a plain text error response (for non-JSON endpoints like M3U/XML)

    Args:
        message: User-friendly error message
        status_code: HTTP status code

    Returns:
        Response object
    """
    return Response(message, status=status_code)


# ============================================================================
# Error Handler Decorator
# ============================================================================


def handle_errors(
    return_json=True, default_message="An error occurred", log_errors=True, include_traceback_in_dev=False
):
    """
    Decorator to handle exceptions in route handlers

    Usage:
        @app.route('/api/resource')
        @handle_errors()
        def my_route():
            # Your code here
            # Any exception will be caught and returned as error response

    Args:
        return_json: If True, returns JSON error; if False, returns plain text
        default_message: Fallback message if exception has no message
        log_errors: If True, logs errors to logger
        include_traceback_in_dev: If True and app.debug=True, includes traceback

    Returns:
        Decorated function that catches and handles exceptions
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except HTTPException:
                # Let Flask handle HTTP exceptions (abort, get_or_404, etc.)
                raise
            except ServiceUnavailableError as e:
                # Service unavailable (503)
                if log_errors:
                    logger.warning(f"Service unavailable in {f.__name__}: {e}")
                message = str(e) if str(e) else "Service temporarily unavailable"
                if return_json:
                    return error_response(message, 503)
                else:
                    return text_error_response(message, 503)

            except ResourceNotFoundError as e:
                # Resource not found (404)
                if log_errors:
                    logger.warning(f"Resource not found in {f.__name__}: {e}")
                message = str(e) if str(e) else "Resource not found"
                if return_json:
                    return error_response(message, 404)
                else:
                    return text_error_response(message, 404)

            except ValidationError as e:
                # Validation errors (400)
                if log_errors:
                    logger.warning(f"Validation error in {f.__name__}: {e}")
                message = str(e) if str(e) else "Validation error"
                details = e.details if hasattr(e, "details") else None
                if return_json:
                    return error_response(message, 400, details)
                else:
                    return text_error_response(message, 400)

            except AuthorizationError as e:
                # Authorization errors (403)
                if log_errors:
                    logger.warning(f"Authorization error in {f.__name__}: {e}")
                message = str(e) if str(e) else "Not authorized"
                if return_json:
                    return error_response(message, 403)
                else:
                    return text_error_response(message, 403)

            except ValueError as e:
                # Validation or business logic errors (400)
                if log_errors:
                    logger.warning(f"Value error in {f.__name__}: {e}")
                message = str(e) if str(e) else default_message
                if return_json:
                    return error_response(message, 400)
                else:
                    return text_error_response(message, 400)

            except PermissionError as e:
                # Authorization errors (403)
                if log_errors:
                    logger.warning(f"Permission error in {f.__name__}: {e}")
                message = str(e) if str(e) else "Permission denied"
                if return_json:
                    return error_response(message, 403)
                else:
                    return text_error_response(message, 403)

            except FileNotFoundError as e:
                # Resource not found (404)
                if log_errors:
                    logger.warning(f"Not found in {f.__name__}: {e}")
                message = str(e) if str(e) else "Resource not found"
                if return_json:
                    return error_response(message, 404)
                else:
                    return text_error_response(message, 404)

            except Exception as exc:
                # Unexpected errors (500)
                if log_errors:
                    logger.error(f"Unexpected error in {f.__name__}", exc_info=True)

                # Never expose internal error details in production
                # But log them for debugging
                from flask import current_app

                if current_app.config.get("DEBUG") and include_traceback_in_dev:
                    details = {"exception_type": type(exc).__name__, "traceback": traceback.format_exc()}
                    if return_json:
                        return error_response(str(exc), 500, details)
                    else:
                        return text_error_response(f"{str(exc)}\n\n{traceback.format_exc()}", 500)
                else:
                    # Production: generic message
                    message = default_message if default_message else "An internal error occurred"
                    if return_json:
                        return error_response(message, 500)
                    else:
                        return text_error_response(message, 500)

        return wrapper

    return decorator


# ============================================================================
# Specific Error Classes (for raising)
# ============================================================================


class ResourceNotFoundError(Exception):
    """Raise when a requested resource doesn't exist (404)"""

    pass


class ValidationError(ValueError):
    """Raise when input validation fails (400)"""

    pass


class AuthorizationError(PermissionError):
    """Raise when user lacks permission (403)"""

    pass


class ServiceUnavailableError(Exception):
    """Raise when service/dependency is unavailable (503)"""

    pass


# ============================================================================
# Flask Error Handlers (register these in app.py)
# ============================================================================


def register_error_handlers(app):
    """
    Register global error handlers for the Flask app

    Call this in app.py after creating the Flask app:
        register_error_handlers(app)
    """

    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors"""
        return error_response("Resource not found", 404)

    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 errors"""
        return error_response("Permission denied", 403)

    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 errors"""
        return error_response("Bad request", 400)

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        logger.error(f"Internal server error: {error}", exc_info=True)

        # Never expose internal errors in production
        if app.config.get("DEBUG"):
            return error_response(str(error), 500)
        else:
            return error_response("An internal error occurred", 500)

    @app.errorhandler(503)
    def service_unavailable(error):
        """Handle 503 errors"""
        return error_response("Service temporarily unavailable", 503)


# ============================================================================
# Database Error Helpers
# ============================================================================


def handle_db_error(e, operation="database operation"):
    """
    Handle database errors safely

    Args:
        e: The exception
        operation: Description of what was being attempted

    Returns:
        tuple: (error_message, status_code)
    """
    from sqlalchemy.exc import IntegrityError, OperationalError

    if isinstance(e, IntegrityError):
        # Constraint violation (e.g., duplicate, foreign key)
        logger.warning(f"Database integrity error during {operation}: {e}")
        return "Database constraint violation. Check for duplicates or invalid references.", 400

    elif isinstance(e, OperationalError):
        # Database connection or operational issues
        logger.error(f"Database operational error during {operation}: {e}", exc_info=True)
        return "Database is temporarily unavailable", 503

    else:
        # Other database errors
        logger.error(f"Database error during {operation}: {e}", exc_info=True)
        return "A database error occurred", 500

"""
Tests for error_handling module
"""
from flask import Flask

from error_handling import (
    AuthorizationError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
    error_response,
    handle_errors,
    text_error_response,
)


def test_error_response_basic():
    """Test basic error response format"""
    app = Flask(__name__)

    with app.app_context():
        response, status_code = error_response("Test error", 400)
        data = response.get_json()

        assert status_code == 400
        assert data["success"] is False
        assert data["error"] == "Test error"
        assert "details" not in data


def test_error_response_with_details():
    """Test error response with additional details"""
    app = Flask(__name__)

    with app.app_context():
        details = {"field": "email", "reason": "invalid format"}
        response, status_code = error_response("Validation failed", 422, details)
        data = response.get_json()

        assert status_code == 422
        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert data["details"] == details


def test_text_error_response():
    """Test plain text error response"""
    response = text_error_response("Service unavailable", 503)

    assert response.status_code == 503
    assert response.data == b"Service unavailable"
    assert response.content_type.startswith("text/")


def test_handle_errors_with_validation_error():
    """Test handle_errors decorator catches ValidationError"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=True)
        def test_func():
            raise ValidationError("Invalid input")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 400
        assert data["success"] is False
        assert "invalid input" in data["error"].lower()


def test_handle_errors_with_resource_not_found():
    """Test handle_errors decorator catches ResourceNotFoundError"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=True)
        def test_func():
            raise ResourceNotFoundError("Item not found")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 404
        assert data["success"] is False
        assert "not found" in data["error"].lower()


def test_handle_errors_with_service_unavailable():
    """Test handle_errors decorator catches ServiceUnavailableError"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=True)
        def test_func():
            raise ServiceUnavailableError("Service down")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 503
        assert data["success"] is False
        assert "service" in data["error"].lower()


def test_handle_errors_with_authorization_error():
    """Test handle_errors decorator catches AuthorizationError"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=True)
        def test_func():
            raise AuthorizationError("Not authorized")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 403
        assert data["success"] is False
        assert "not authorized" in data["error"].lower()


def test_handle_errors_with_value_error():
    """Test handle_errors decorator catches ValueError"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=True)
        def test_func():
            raise ValueError("Invalid value")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 400
        assert data["success"] is False
        assert "invalid value" in data["error"].lower()


def test_handle_errors_with_permission_error():
    """Test handle_errors decorator catches PermissionError"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=True)
        def test_func():
            raise PermissionError("Permission denied")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 403
        assert data["success"] is False
        assert "permission" in data["error"].lower()


def test_handle_errors_with_file_not_found():
    """Test handle_errors decorator catches FileNotFoundError"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=True)
        def test_func():
            raise FileNotFoundError("File missing")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 404
        assert data["success"] is False
        assert "file missing" in data["error"].lower()


def test_handle_errors_text_response():
    """Test handle_errors decorator with text response"""
    app = Flask(__name__)

    with app.app_context():

        @handle_errors(return_json=False, default_message="Error occurred")
        def test_func():
            raise ValueError("Bad input")

        response = test_func()

        assert response.status_code == 400
        assert b"Bad input" in response.data


def test_handle_errors_generic_exception():
    """Test handle_errors decorator catches generic exceptions"""
    app = Flask(__name__)
    app.config["DEBUG"] = False

    with app.app_context():

        @handle_errors(return_json=True, default_message="Something went wrong")
        def test_func():
            raise Exception("Unexpected error")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 500
        assert data["success"] is False
        assert data["error"] == "Something went wrong"  # Generic message in production


def test_handle_errors_generic_exception_debug_mode():
    """Test handle_errors decorator in debug mode includes traceback"""
    app = Flask(__name__)
    app.config["DEBUG"] = True

    with app.app_context():

        @handle_errors(return_json=True, include_traceback_in_dev=True)
        def test_func():
            raise Exception("Debug error")

        response, status_code = test_func()
        data = response.get_json()

        assert status_code == 500
        assert data["success"] is False
        assert "debug error" in data["error"].lower()
        assert "details" in data
        assert "traceback" in data["details"]


def test_validation_error_with_details():
    """Test ValidationError can include details"""
    error = ValidationError("Invalid data")
    error.details = {"field": "name", "constraint": "required"}

    assert str(error) == "Invalid data"
    assert error.details["field"] == "name"


def test_custom_exceptions_are_exceptions():
    """Test custom exceptions inherit from Exception"""
    assert issubclass(ValidationError, Exception)
    assert issubclass(ResourceNotFoundError, Exception)
    assert issubclass(ServiceUnavailableError, Exception)
    assert issubclass(AuthorizationError, Exception)

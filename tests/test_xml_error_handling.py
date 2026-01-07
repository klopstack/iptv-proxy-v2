"""
Tests for XML error handling in EPG endpoints.

Verifies that:
1. XML endpoints return valid XMLTV on errors (not plain text)
2. Error details are logged but not exposed in the response
3. Jellyfin XML parser can parse error responses without exceptions
"""

import logging
import xml.etree.ElementTree as ET

import pytest
from flask import Flask

from error_handling import (
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
    handle_xml_errors,
    xml_error_response,
)


class TestXmlErrorResponse:
    """Test the xml_error_response function"""

    def test_returns_valid_xmltv(self):
        """xml_error_response returns valid XMLTV XML"""
        response = xml_error_response("Test error", 500)
        data = response.get_data(as_text=True)

        # Should be valid XML
        tree = ET.fromstring(data.encode())
        assert tree.tag == "tv"
        assert tree.get("generator-info-name") == "iptv-proxy-v2"

    def test_has_correct_content_type(self):
        """xml_error_response sets correct Content-Type"""
        response = xml_error_response("Test error", 500)
        assert response.content_type == "application/xml; charset=utf-8"

    def test_has_correct_status_code(self):
        """xml_error_response respects status_code parameter"""
        response_503 = xml_error_response("Service down", 503)
        assert response_503.status_code == 503

        response_400 = xml_error_response("Bad request", 400)
        assert response_400.status_code == 400

    def test_does_not_expose_error_details(self):
        """xml_error_response does not include error message in XML"""
        error_msg = "Database connection failed"
        response = xml_error_response(error_msg, 500)
        data = response.get_data(as_text=True)

        # Error message should NOT be in the response
        assert error_msg not in data
        assert "Database" not in data

    def test_is_parseable_by_jellyfin(self):
        """xml_error_response produces XML that Jellyfin can parse"""
        response = xml_error_response("Any error", 500)
        data = response.get_data(as_text=True)

        # This should NOT raise an exception like Jellyfin would encounter
        try:
            tree = ET.fromstring(data.encode())
            assert tree is not None
            # Successfully parsed - Jellyfin would not fail
        except ET.ParseError:
            pytest.fail("XML should be valid and parseable")


class TestHandleXmlErrors:
    """Test the handle_xml_errors decorator"""

    @pytest.fixture
    def app_with_handler(self):
        """Create a Flask app with an endpoint using handle_xml_errors"""
        app = Flask(__name__)

        @app.route("/test/success")
        @handle_xml_errors()
        def success():
            return "<?xml version='1.0'?><tv></tv>", 200, {"Content-Type": "application/xml"}

        @app.route("/test/service_unavailable")
        @handle_xml_errors()
        def service_unavailable():
            raise ServiceUnavailableError("Database is down")

        @app.route("/test/not_found")
        @handle_xml_errors()
        def not_found():
            raise ResourceNotFoundError("Channel not found")

        @app.route("/test/validation_error")
        @handle_xml_errors()
        def validation_error():
            raise ValidationError("Invalid parameter")

        @app.route("/test/generic_error")
        @handle_xml_errors(default_message="Error generating EPG")
        def generic_error():
            raise ValueError("Some internal error")

        @app.route("/test/unexpected_error")
        @handle_xml_errors()
        def unexpected_error():
            raise RuntimeError("Totally unexpected error")

        return app

    def test_success_passes_through(self, app_with_handler):
        """Successful responses pass through unchanged"""
        client = app_with_handler.test_client()
        response = client.get("/test/success")

        assert response.status_code == 200
        assert response.content_type == "application/xml"
        # Should get the actual response, not an error response
        data = response.get_data(as_text=True)
        assert "<tv>" in data

    def test_service_unavailable_returns_valid_xml(self, app_with_handler):
        """ServiceUnavailableError returns valid XMLTV"""
        client = app_with_handler.test_client()
        response = client.get("/test/service_unavailable")

        assert response.status_code == 503
        assert response.content_type == "application/xml; charset=utf-8"

        data = response.get_data(as_text=True)
        tree = ET.fromstring(data.encode())
        assert tree.tag == "tv"

    def test_not_found_returns_valid_xml(self, app_with_handler):
        """ResourceNotFoundError returns valid XMLTV"""
        client = app_with_handler.test_client()
        response = client.get("/test/not_found")

        assert response.status_code == 404
        tree = ET.fromstring(response.get_data())
        assert tree.tag == "tv"

    def test_validation_error_returns_valid_xml(self, app_with_handler):
        """ValidationError returns valid XMLTV"""
        client = app_with_handler.test_client()
        response = client.get("/test/validation_error")

        assert response.status_code == 400
        tree = ET.fromstring(response.get_data())
        assert tree.tag == "tv"

    def test_generic_error_returns_valid_xml(self, app_with_handler):
        """Generic exceptions return valid XMLTV"""
        client = app_with_handler.test_client()
        response = client.get("/test/generic_error")

        assert response.status_code == 400
        tree = ET.fromstring(response.get_data())
        assert tree.tag == "tv"

    def test_unexpected_error_returns_valid_xml(self, app_with_handler):
        """Unexpected exceptions return valid XMLTV"""
        client = app_with_handler.test_client()
        response = client.get("/test/unexpected_error")

        assert response.status_code == 500
        tree = ET.fromstring(response.get_data())
        assert tree.tag == "tv"

    def test_errors_are_logged(self, app_with_handler, caplog):
        """Errors are logged for debugging"""
        client = app_with_handler.test_client()

        with caplog.at_level(logging.WARNING):
            response = client.get("/test/service_unavailable")
            assert response.status_code == 503

        # Should have logged the error
        assert "Database is down" in caplog.text

    def test_unexpected_errors_logged_with_traceback(self, app_with_handler, caplog):
        """Unexpected errors are logged with traceback"""
        client = app_with_handler.test_client()

        with caplog.at_level(logging.ERROR):
            response = client.get("/test/unexpected_error")
            assert response.status_code == 500

        # Should have logged as ERROR with traceback
        assert "Totally unexpected error" in caplog.text or "RuntimeError" in caplog.text


class TestJellyfinCompatibility:
    """Test that error responses are compatible with Jellyfin's XML parser"""

    def test_jellyfin_can_parse_error_response(self):
        """Jellyfin should be able to parse our error responses"""
        response = xml_error_response("Any error", 500)
        data = response.get_data()

        # Simulate what Jellyfin does when parsing XMLTV
        try:
            # This is similar to System.Xml.XmlTextReaderImpl.ParseRootLevelWhitespace()
            tree = ET.fromstring(data)
            # If we get here, Jellyfin won't throw XmlException
            assert tree is not None
        except ET.ParseError as e:
            pytest.fail(f"Jellyfin would fail to parse this response: {e}")

    def test_error_response_is_not_plain_text(self):
        """Error response is XML, not plain text"""
        response = xml_error_response("Error", 500)
        data = response.get_data(as_text=True)

        # Should start with XML declaration, not plain text
        assert data.startswith("<?xml")
        assert "<tv" in data
        assert "</tv>" in data

    def test_minimal_but_valid_xmltv(self):
        """Response is minimal but valid XMLTV"""
        response = xml_error_response("Error", 500)
        data = response.get_data(as_text=True)

        # Should have required elements
        tree = ET.fromstring(data.encode())
        assert tree.tag == "tv"
        assert tree.get("generator-info-name") == "iptv-proxy-v2"

        # Should have no channel or programme elements (empty EPG)
        channels = tree.findall("channel")
        programmes = tree.findall("programme")
        assert len(channels) == 0
        assert len(programmes) == 0

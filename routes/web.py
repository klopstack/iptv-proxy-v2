"""
Web UI routes (template rendering)
"""
from flask import Blueprint, render_template

# Create blueprint
web_bp = Blueprint("web", __name__)


@web_bp.route("/")
def index():
    """Main page"""
    return render_template("index.html")


@web_bp.route("/accounts")
def accounts_page():
    """Accounts management page"""
    return render_template("accounts.html")


@web_bp.route("/filters")
def filters_page():
    """Filters management page"""
    return render_template("filters.html")


@web_bp.route("/test")
def test_page():
    """Test and preview page"""
    return render_template("test.html")


@web_bp.route("/rulesets")
def rulesets_page():
    """Rulesets and tags management page"""
    return render_template("rulesets.html")

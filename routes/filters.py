"""
Filter management routes
"""
import logging

from flask import Blueprint, request

from api_responses import data_response, no_content, success_response
from models import Account, Filter, db
from schemas import FilterCreateSchema, FilterUpdateSchema, validate_request_data
from services.cache_service import cache_service
from services.filter_service import FilterService

logger = logging.getLogger(__name__)

filters_bp = Blueprint("filters", __name__)


def _serialize_filter(filter_obj):
    return {
        "id": filter_obj.id,
        "account_id": filter_obj.account_id,
        "name": filter_obj.name,
        "filter_type": filter_obj.filter_type,
        "filter_action": filter_obj.filter_action,
        "filter_value": filter_obj.filter_value,
        "enabled": filter_obj.enabled,
    }


@filters_bp.route("/api/filters", methods=["GET"])
def get_filters():
    """Get all filters"""
    filters = Filter.query.all()
    return data_response([_serialize_filter(f) for f in filters])


@filters_bp.route("/api/filters", methods=["POST"])
@validate_request_data(FilterCreateSchema)
def create_filter():
    """Create a new filter"""
    data = request.validated_data

    db.get_or_404(Account, data["account_id"])

    filter_obj = Filter(
        account_id=data["account_id"],
        name=data["name"],
        filter_type=data["filter_type"],
        filter_action=data["filter_action"],
        filter_value=data["filter_value"],
        enabled=data.get("enabled", True),
    )

    db.session.add(filter_obj)
    db.session.commit()

    FilterService.compute_visibility_for_account(data["account_id"])
    cache_service.clear_account_cache(data["account_id"])

    return success_response(_serialize_filter(filter_obj), status_code=201)


@filters_bp.route("/api/filters/<int:filter_id>", methods=["PUT"])
@validate_request_data(FilterUpdateSchema)
def update_filter(filter_id):
    """Update a filter"""
    filter_obj = db.get_or_404(Filter, filter_id)
    data = request.validated_data

    filter_obj.name = data.get("name", filter_obj.name)
    filter_obj.filter_type = data.get("filter_type", filter_obj.filter_type)
    filter_obj.filter_action = data.get("filter_action", filter_obj.filter_action)
    filter_obj.filter_value = data.get("filter_value", filter_obj.filter_value)
    filter_obj.enabled = data.get("enabled", filter_obj.enabled)

    db.session.commit()

    FilterService.compute_visibility_for_account(filter_obj.account_id)
    cache_service.clear_account_cache(filter_obj.account_id)

    return success_response(_serialize_filter(filter_obj))


@filters_bp.route("/api/filters/<int:filter_id>", methods=["DELETE"])
def delete_filter(filter_id):
    """Delete a filter"""
    filter_obj = db.get_or_404(Filter, filter_id)
    account_id = filter_obj.account_id

    db.session.delete(filter_obj)
    db.session.commit()

    FilterService.compute_visibility_for_account(account_id)
    cache_service.clear_account_cache(account_id)

    return no_content()

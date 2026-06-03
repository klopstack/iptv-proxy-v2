"""Shared helpers for registering repetitive JSON CRUD route handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flask import Blueprint, abort, jsonify, request


def register_json_crud_routes(
    bp: Blueprint,
    *,
    base_path: str,
    id_param: str,
    list_fn: Callable[[], list[dict[str, Any]]],
    get_fn: Callable[[int], dict[str, Any] | None],
    create_fn: Callable[[dict[str, Any]], tuple[dict[str, Any] | None, str | None, int]],
    update_fn: Callable[[int, dict[str, Any]], tuple[dict[str, Any] | None, str | None, int]],
    delete_fn: Callable[[int], bool],
) -> None:
    """Register GET list, GET one, POST, PUT, DELETE handlers on *bp*."""

    @bp.route(base_path, methods=["GET"], endpoint=f"list_{base_path.strip('/').replace('/', '_')}")
    def _list_items():
        return jsonify(list_fn())

    @bp.route(base_path, methods=["POST"], endpoint=f"create_{base_path.strip('/').replace('/', '_')}")
    def _create_item():
        payload, error, status = create_fn(request.get_json() or {})
        if error:
            return jsonify({"error": error}), status
        return jsonify(payload), status

    @bp.route(f"{base_path}/<{id_param}>", methods=["GET"], endpoint=f"get_{base_path.strip('/').replace('/', '_')}")
    def _get_item(**kwargs):
        item_id = kwargs[id_param]
        payload = get_fn(item_id)
        if payload is None:
            abort(404)
        return jsonify(payload)

    @bp.route(f"{base_path}/<{id_param}>", methods=["PUT"], endpoint=f"update_{base_path.strip('/').replace('/', '_')}")
    def _update_item(**kwargs):
        item_id = kwargs[id_param]
        payload, error, status = update_fn(item_id, request.get_json() or {})
        if error:
            if status == 404:
                abort(404)
            return jsonify({"error": error}), status
        return jsonify(payload), status

    @bp.route(
        f"{base_path}/<{id_param}>", methods=["DELETE"], endpoint=f"delete_{base_path.strip('/').replace('/', '_')}"
    )
    def _delete_item(**kwargs):
        item_id = kwargs[id_param]
        if not delete_fn(item_id):
            abort(404)
        return "", 204

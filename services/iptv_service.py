"""
IPTV API Service - handles communication with Xtream Codes servers
"""

import logging

import requests

logger = logging.getLogger(__name__)


class IPTVService:
    """Service for interacting with Xtream Codes API"""

    def __init__(self, server, username, password, user_agent="okhttp/3.14.9"):
        self.server = server
        self.username = username
        self.password = password
        self.user_agent = user_agent
        self.base_url = f"http://{server}"

    def _make_request(self, action, params=None):
        """Make API request to Xtream Codes server"""
        url = f"{self.base_url}/player_api.php"

        request_params = {"username": self.username, "password": self.password}

        if action:
            request_params["action"] = action

        if params:
            request_params.update(params)

        headers = {"User-Agent": self.user_agent}

        logger.debug(f"Making request to {url} with action={action}")

        response = requests.get(url, params=request_params, headers=headers, timeout=30)
        response.raise_for_status()

        return response.json()

    def authenticate(self):
        """Authenticate and get server/user info"""
        return self._make_request(None)

    def get_live_categories(self):
        """Get all live stream categories"""
        return self._make_request("get_live_categories")

    def get_live_streams(self, category_id=None):
        """Get all live streams, optionally filtered by category"""
        params = {}
        if category_id:
            params["category_id"] = category_id
        return self._make_request("get_live_streams", params)

    def get_vod_categories(self):
        """Get all VOD categories"""
        return self._make_request("get_vod_categories")

    def get_vod_streams(self, category_id=None):
        """Get all VOD streams"""
        params = {}
        if category_id:
            params["category_id"] = category_id
        return self._make_request("get_vod_streams", params)

    def get_series_categories(self):
        """Get all series categories"""
        return self._make_request("get_series_categories")

    def get_series(self, category_id=None):
        """Get all series"""
        params = {}
        if category_id:
            params["category_id"] = category_id
        return self._make_request("get_series", params)

    def get_xmltv(self):
        """Get XMLTV EPG data"""
        url = f"{self.base_url}/xmltv.php"
        params = {"username": self.username, "password": self.password}
        headers = {"User-Agent": "9XtreamPlayer"}

        response = requests.get(url, params=params, headers=headers, timeout=120)
        response.raise_for_status()

        return response.content

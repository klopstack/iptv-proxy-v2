#!/usr/bin/env python3
"""Test Flask route matching with special characters"""
from flask import Flask

app = Flask(__name__)


@app.route("/live/<username>/<password>/<int:stream_id>.<ext>", methods=["GET"])
def test_route(username, password, stream_id, ext):
    return f"Matched: username={username}, password={password}, stream_id={stream_id}, ext={ext}"


if __name__ == "__main__":
    # Test with werkzeug's test client
    with app.test_client() as client:
        # Test with ! in password
        response = client.get("/live/office/things2watch!/7234.ts")
        print(f"Test 1 (with !): {response.status_code} - {response.data}")

        # Test with encoded !
        response = client.get("/live/office/things2watch%21/7234.ts")
        print(f"Test 2 (encoded !): {response.status_code} - {response.data}")

        # Test without special char
        response = client.get("/live/office/things2watch/7234.ts")
        print(f"Test 3 (no special): {response.status_code} - {response.data}")

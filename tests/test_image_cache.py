"""
Tests for image cache service and routes
"""
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import app
from models import CachedImage, db


@pytest.fixture
def client():
    """Create a test client with in-memory database and temp cache dir"""
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True

    with tempfile.TemporaryDirectory() as tmpdir:
        # Reset the global image cache instance
        import services.image_cache_service as cache_module

        cache_module._image_cache = None

        # Patch the default cache dir to use temp directory
        with patch.dict("os.environ", {"IMAGE_CACHE_DIR": tmpdir}):
            with app.test_client() as client:
                with app.app_context():
                    db.create_all()
                    yield client
                    db.session.remove()
                    db.drop_all()

            # Reset singleton after tests
            cache_module._image_cache = None


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for image cache"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestImageCacheService:
    """Tests for ImageCacheService"""

    def test_hash_url(self):
        """Test URL hashing produces consistent results"""
        from services.image_cache_service import ImageCacheService

        url = "https://example.com/icon.png"
        hash1 = ImageCacheService.hash_url(url)
        hash2 = ImageCacheService.hash_url(url)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex chars
        assert all(c in "0123456789abcdef" for c in hash1)

    def test_hash_url_different_urls(self):
        """Test different URLs produce different hashes"""
        from services.image_cache_service import ImageCacheService

        hash1 = ImageCacheService.hash_url("https://example.com/icon1.png")
        hash2 = ImageCacheService.hash_url("https://example.com/icon2.png")

        assert hash1 != hash2

    def test_get_file_path(self, temp_cache_dir):
        """Test file path generation with two-level directory structure"""
        from services.image_cache_service import ImageCacheService

        service = ImageCacheService(cache_dir=temp_cache_dir)
        url_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

        path = service.get_file_path(url_hash, ".png")

        assert "ab" in str(path)  # First 2 chars as subdirectory
        assert path.name == url_hash + ".png"

    def test_is_valid_url(self, temp_cache_dir):
        """Test URL validation"""
        from services.image_cache_service import ImageCacheService

        service = ImageCacheService(cache_dir=temp_cache_dir)

        assert service._is_valid_url("https://example.com/icon.png") is True
        assert service._is_valid_url("http://example.com/icon.png") is True
        assert service._is_valid_url("ftp://example.com/icon.png") is False
        assert service._is_valid_url("") is False
        assert service._is_valid_url(None) is False
        assert service._is_valid_url("not-a-url") is False

    def test_get_extension(self, temp_cache_dir):
        """Test content type to extension mapping"""
        from services.image_cache_service import ImageCacheService

        service = ImageCacheService(cache_dir=temp_cache_dir)

        assert service._get_extension("image/png") == ".png"
        assert service._get_extension("image/jpeg") == ".jpg"
        assert service._get_extension("image/gif") == ".gif"
        assert service._get_extension("image/webp") == ".webp"
        assert service._get_extension("image/svg+xml") == ".svg"
        assert service._get_extension("unknown/type") == ".img"

    def test_detect_content_type(self, temp_cache_dir):
        """Test content type detection from file header"""
        from services.image_cache_service import ImageCacheService

        service = ImageCacheService(cache_dir=temp_cache_dir)

        # PNG magic bytes
        assert service._detect_content_type(b"\x89PNG\r\n\x1a\n") == "image/png"
        # JPEG magic bytes
        assert service._detect_content_type(b"\xff\xd8\xff") == "image/jpeg"
        # GIF magic bytes
        assert service._detect_content_type(b"GIF89a") == "image/gif"
        assert service._detect_content_type(b"GIF87a") == "image/gif"
        # Unknown
        assert service._detect_content_type(b"unknown") == "application/octet-stream"

    def test_get_proxy_url(self, temp_cache_dir):
        """Test proxy URL generation"""
        from services.image_cache_service import ImageCacheService

        service = ImageCacheService(cache_dir=temp_cache_dir)
        original_url = "https://example.com/icon.png"
        base_url = "http://localhost:8000"

        proxy_url = service.get_proxy_url(original_url, base_url)
        url_hash = service.hash_url(original_url)

        assert proxy_url == f"http://localhost:8000/icon/{url_hash}"

    def test_get_proxy_url_invalid(self, temp_cache_dir):
        """Test proxy URL returns original for invalid URLs"""
        from services.image_cache_service import ImageCacheService

        service = ImageCacheService(cache_dir=temp_cache_dir)

        assert service.get_proxy_url("", "http://localhost:8000") == ""
        assert service.get_proxy_url("not-a-url", "http://localhost:8000") == "not-a-url"


class TestImageCacheServiceWithDB:
    """Tests for ImageCacheService that require database"""

    def test_cache_image_success(self, client, temp_cache_dir):
        """Test successful image caching"""
        from services.image_cache_service import ImageCacheService

        with app.app_context():
            service = ImageCacheService(cache_dir=temp_cache_dir)

            # Mock the HTTP request
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "image/png", "Content-Length": "100"}
            mock_response.iter_content = MagicMock(return_value=[b"\x89PNG\r\n\x1a\n" + b"x" * 92])

            with patch("requests.get", return_value=mock_response):
                url = "https://example.com/test-icon.png"
                url_hash = service.cache_image(url)

            assert url_hash is not None
            assert len(url_hash) == 64

            # Verify database entry
            cached = CachedImage.query.filter_by(url_hash=url_hash).first()
            assert cached is not None
            assert cached.status == "cached"
            assert cached.original_url == url
            assert cached.content_type == "image/png"
            assert cached.fetch_count == 1

    def test_cache_image_already_cached(self, client, temp_cache_dir):
        """Test that already cached images are not re-fetched"""
        from services.image_cache_service import ImageCacheService

        with app.app_context():
            service = ImageCacheService(cache_dir=temp_cache_dir)
            url = "https://example.com/cached-icon.png"
            url_hash = service.hash_url(url)

            # Create a cached entry
            cached = CachedImage(
                url_hash=url_hash,
                original_url=url,
                status="cached",
                content_type="image/png",
                file_path="ab/test.png",
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            db.session.add(cached)
            db.session.commit()

            # Should not make HTTP request
            with patch("requests.get") as mock_get:
                result = service.cache_image(url)
                mock_get.assert_not_called()

            assert result == url_hash

    def test_get_stats(self, client, temp_cache_dir):
        """Test cache statistics"""
        from services.image_cache_service import ImageCacheService

        with app.app_context():
            service = ImageCacheService(cache_dir=temp_cache_dir)

            # Add some test entries
            for i, status in enumerate(["cached", "cached", "error", "expired"]):
                cached = CachedImage(
                    url_hash=f"hash{i}" + "0" * 59,
                    original_url=f"https://example.com/icon{i}.png",
                    status=status,
                    file_size=1000 if status == "cached" else None,
                )
                db.session.add(cached)
            db.session.commit()

            stats = service.get_stats()

            assert stats["total_entries"] == 4
            assert stats["cached"] == 2
            assert stats["errors"] == 1
            assert stats["expired"] == 1
            assert stats["total_size_bytes"] == 2000


class TestImageRoutes:
    """Tests for image cache API routes"""

    def test_serve_cached_icon_invalid_hash(self, client):
        """Test serving icon with invalid hash format"""
        response = client.get("/icon/invalid")
        assert response.status_code == 400

        response = client.get("/icon/tooshort")
        assert response.status_code == 400

    def test_serve_cached_icon_not_found(self, client):
        """Test serving icon that doesn't exist"""
        valid_hash = "a" * 64
        response = client.get(f"/icon/{valid_hash}")
        assert response.status_code == 404

    def test_get_cache_stats(self, client):
        """Test cache stats endpoint"""
        response = client.get("/api/image-cache/stats")
        assert response.status_code == 200

        data = response.get_json()
        assert "total_entries" in data
        assert "cached" in data
        assert "total_size_bytes" in data

    def test_list_cache_entries(self, client):
        """Test listing cache entries"""
        response = client.get("/api/image-cache/entries")
        assert response.status_code == 200

        data = response.get_json()
        assert "total" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_list_cache_entries_with_filter(self, client):
        """Test listing cache entries with status filter"""
        with app.app_context():
            # Add test entries
            for i, status in enumerate(["cached", "error"]):
                cached = CachedImage(
                    url_hash=f"hash{i}" + "0" * 59,
                    original_url=f"https://example.com/icon{i}.png",
                    status=status,
                )
                db.session.add(cached)
            db.session.commit()

        response = client.get("/api/image-cache/entries?status=cached")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] == 1
        assert all(e["status"] == "cached" for e in data["entries"])

    def test_fetch_and_cache_icon_no_url(self, client):
        """Test fetch endpoint without URL"""
        response = client.post("/icon/fetch", json={})
        assert response.status_code == 400

        data = response.get_json()
        assert "error" in data

    def test_cleanup_cache(self, client):
        """Test cache cleanup endpoint"""
        with app.app_context():
            # Add expired entry
            cached = CachedImage(
                url_hash="expired" + "0" * 57,
                original_url="https://example.com/old.png",
                status="cached",
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            db.session.add(cached)
            db.session.commit()

        response = client.post("/api/image-cache/cleanup?delete_files=false")
        assert response.status_code == 200

        data = response.get_json()
        assert data["success"] is True
        assert data["removed_count"] >= 1

    def test_delete_cache_entry(self, client):
        """Test deleting a cache entry"""
        with app.app_context():
            cached = CachedImage(
                url_hash="todelete" + "0" * 56,
                original_url="https://example.com/delete.png",
                status="cached",
            )
            db.session.add(cached)
            db.session.commit()
            entry_id = cached.id

        response = client.delete(f"/api/image-cache/entries/{entry_id}")
        assert response.status_code == 200

        # Verify deleted
        with app.app_context():
            assert CachedImage.query.get(entry_id) is None

    def test_delete_cache_entry_not_found(self, client):
        """Test deleting non-existent cache entry"""
        response = client.delete("/api/image-cache/entries/99999")
        assert response.status_code == 404


class TestPlaylistIconProxy:
    """Tests for playlist generation with icon proxying"""

    def test_playlist_with_proxy_icons(self, client):
        """Test that proxy_icons parameter rewrites icon URLs"""
        from models import Account, Category, Channel, Credential

        with app.app_context():
            # Create test account with channel
            account = Account(name="Test Account", server="test.example.com", enabled=True)
            db.session.add(account)
            db.session.flush()

            credential = Credential(account_id=account.id, username="testuser", password="testpass", max_connections=1)
            db.session.add(credential)

            category = Category(account_id=account.id, category_id="1", category_name="Test Category")
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test Channel",
                cleaned_name="Test Channel",
                stream_icon="https://external.com/icon.png",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

            account_id = account.id

        # Test without proxy_icons - should have original URL
        response = client.get(f"/playlist/{account_id}.m3u")
        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert "https://external.com/icon.png" in content

        # Test with proxy_icons - should have proxied URL
        response = client.get(f"/playlist/{account_id}.m3u?proxy_icons=true")
        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert "/icon/" in content
        assert "https://external.com/icon.png" not in content

"""
Tests for XMLTV Grabber Service
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.xmltv_grabber_service import GRABBER_CONFIG_DIR, GrabberConfig, XmltvGrabber, XmltvGrabberService


class TestXmltvGrabberDataclasses:
    """Test dataclass definitions"""

    def test_xmltv_grabber_dataclass(self):
        """Test XmltvGrabber dataclass creation"""
        grabber = XmltvGrabber(
            name="tv_grab_test",
            description="Test grabber",
            path="/usr/bin/tv_grab_test",
            capabilities=["baseline", "manualconfig"],
        )
        assert grabber.name == "tv_grab_test"
        assert grabber.description == "Test grabber"
        assert grabber.path == "/usr/bin/tv_grab_test"
        assert grabber.capabilities == ["baseline", "manualconfig"]

    def test_grabber_config_dataclass(self):
        """Test GrabberConfig dataclass creation"""
        config = GrabberConfig(
            grabber_name="tv_grab_test",
            config_file="/path/to/config",
            channels=[{"id": "ch1", "name": "Channel 1"}],
            options={"days": 7},
        )
        assert config.grabber_name == "tv_grab_test"
        assert config.config_file == "/path/to/config"
        assert len(config.channels) == 1
        assert config.options["days"] == 7


class TestXmltvGrabberService:
    """Test XmltvGrabberService methods"""

    @patch("os.path.isdir")
    @patch("os.listdir")
    @patch("os.access")
    @patch.object(XmltvGrabberService, "_get_grabber_info")
    def test_get_installed_grabbers(self, mock_get_info, mock_access, mock_listdir, mock_isdir):
        """Test discovering installed grabbers"""
        # Only return True for one directory to simplify the test
        mock_isdir.side_effect = lambda p: p == "/usr/bin"
        mock_listdir.return_value = ["tv_grab_test1", "tv_grab_test2", "other_file"]
        mock_access.return_value = True
        mock_get_info.side_effect = [
            XmltvGrabber("tv_grab_test1", "Test 1", "/usr/bin/tv_grab_test1", []),
            XmltvGrabber("tv_grab_test2", "Test 2", "/usr/bin/tv_grab_test2", []),
        ]

        grabbers = XmltvGrabberService.get_installed_grabbers()

        assert len(grabbers) == 2
        # Should be sorted by name
        names = [g.name for g in grabbers]
        assert names == sorted(names)

    @patch("os.path.isdir")
    def test_get_installed_grabbers_no_directories(self, mock_isdir):
        """Test when no search directories exist"""
        mock_isdir.return_value = False

        grabbers = XmltvGrabberService.get_installed_grabbers()

        assert grabbers == []

    @patch("subprocess.run")
    def test_get_grabber_info_success(self, mock_run):
        """Test getting grabber info successfully"""
        # Mock --description call
        desc_result = MagicMock()
        desc_result.returncode = 0
        desc_result.stdout = "Test grabber description"

        # Mock --capabilities call
        cap_result = MagicMock()
        cap_result.returncode = 0
        cap_result.stdout = "baseline\nmanualconfig\npreferredmethod"

        mock_run.side_effect = [desc_result, cap_result]

        grabber = XmltvGrabberService._get_grabber_info("/usr/bin/tv_grab_test", "tv_grab_test")

        assert grabber is not None
        assert grabber.name == "tv_grab_test"
        assert grabber.description == "Test grabber description"
        assert grabber.capabilities == ["baseline", "manualconfig", "preferredmethod"]

    @patch("subprocess.run")
    def test_get_grabber_info_timeout(self, mock_run):
        """Test handling timeout when getting grabber info"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)

        grabber = XmltvGrabberService._get_grabber_info("/usr/bin/tv_grab_test", "tv_grab_test")

        # Should still return a grabber with default values
        assert grabber is not None
        assert grabber.name == "tv_grab_test"
        assert "tv_grab_test" in grabber.description

    @patch.object(XmltvGrabberService, "get_installed_grabbers")
    def test_get_grabber_by_name_found(self, mock_get_grabbers):
        """Test finding a grabber by name"""
        mock_get_grabbers.return_value = [
            XmltvGrabber("tv_grab_test1", "Test 1", "/usr/bin/tv_grab_test1", []),
            XmltvGrabber("tv_grab_test2", "Test 2", "/usr/bin/tv_grab_test2", []),
        ]

        grabber = XmltvGrabberService.get_grabber_by_name("tv_grab_test2")

        assert grabber is not None
        assert grabber.name == "tv_grab_test2"

    @patch.object(XmltvGrabberService, "get_installed_grabbers")
    def test_get_grabber_by_name_not_found(self, mock_get_grabbers):
        """Test when grabber name is not found"""
        mock_get_grabbers.return_value = [
            XmltvGrabber("tv_grab_test1", "Test 1", "/usr/bin/tv_grab_test1", []),
        ]

        grabber = XmltvGrabberService.get_grabber_by_name("tv_grab_nonexistent")

        assert grabber is None


class TestXmltvGrabberServiceConfig:
    """Test configuration management methods"""

    def test_get_grabber_config_path(self):
        """Test getting config path"""
        path = XmltvGrabberService.get_grabber_config_path("my_config")
        assert path == GRABBER_CONFIG_DIR / "my_config.conf"

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    def test_configure_grabber_not_found(self, mock_get_grabber):
        """Test configuring a non-existent grabber"""
        mock_get_grabber.return_value = None

        success, message = XmltvGrabberService.configure_grabber("nonexistent", "config1")

        assert success is False
        assert "not found" in message

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    def test_configure_grabber_with_data(self, mock_get_grabber):
        """Test configuring grabber with provided data"""
        mock_get_grabber.return_value = XmltvGrabber("tv_grab_test", "Test", "/usr/bin/tv_grab_test", [])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(
                XmltvGrabberService,
                "get_grabber_config_path",
                return_value=Path(tmpdir) / "test.conf",
            ):
                # Patch GRABBER_CONFIG_DIR to use temp directory
                with patch("services.xmltv_grabber_service.GRABBER_CONFIG_DIR", Path(tmpdir)):
                    success, message = XmltvGrabberService.configure_grabber(
                        "tv_grab_test", "test", config_data="test config content"
                    )

                    assert success is True
                    assert "saved" in message.lower()

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    def test_configure_grabber_requires_manual_config(self, mock_get_grabber):
        """Test grabber that requires manual configuration"""
        mock_get_grabber.return_value = XmltvGrabber("tv_grab_test", "Test", "/usr/bin/tv_grab_test", ["manualconfig"])

        with patch("services.xmltv_grabber_service.GRABBER_CONFIG_DIR", Path("/tmp")):
            success, message = XmltvGrabberService.configure_grabber("tv_grab_test", "test")

            assert success is False
            assert "manual configuration" in message.lower()

    def test_list_grabber_configs_no_directory(self):
        """Test listing configs when directory doesn't exist"""
        with patch(
            "services.xmltv_grabber_service.GRABBER_CONFIG_DIR",
            Path("/nonexistent/path"),
        ):
            configs = XmltvGrabberService.list_grabber_configs()
            assert configs == []

    def test_list_grabber_configs_with_files(self):
        """Test listing config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create some config files
            (tmppath / "config1.conf").write_text("config1 content")
            (tmppath / "config2.conf").write_text("config2 content")

            with patch("services.xmltv_grabber_service.GRABBER_CONFIG_DIR", tmppath):
                configs = XmltvGrabberService.list_grabber_configs()

                assert len(configs) == 2
                names = [c["name"] for c in configs]
                assert "config1" in names
                assert "config2" in names

    def test_delete_grabber_config_not_found(self):
        """Test deleting non-existent config"""
        with patch(
            "services.xmltv_grabber_service.GRABBER_CONFIG_DIR",
            Path("/nonexistent/path"),
        ):
            success, message = XmltvGrabberService.delete_grabber_config("nonexistent")

            assert success is False
            assert "not found" in message

    def test_delete_grabber_config_success(self):
        """Test deleting config successfully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            config_file = tmppath / "test.conf"
            config_file.write_text("test content")

            with patch("services.xmltv_grabber_service.GRABBER_CONFIG_DIR", tmppath):
                success, message = XmltvGrabberService.delete_grabber_config("test")

                assert success is True
                assert not config_file.exists()


class TestXmltvGrabberServiceRun:
    """Test grabber execution methods"""

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    def test_run_grabber_not_found(self, mock_get_grabber):
        """Test running a non-existent grabber"""
        mock_get_grabber.return_value = None

        success, content, error = XmltvGrabberService.run_grabber("nonexistent")

        assert success is False
        assert content == b""
        assert "not found" in error

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    @patch("subprocess.run")
    def test_run_grabber_success(self, mock_run, mock_get_grabber):
        """Test running grabber successfully"""
        mock_get_grabber.return_value = XmltvGrabber("tv_grab_test", "Test", "/usr/bin/tv_grab_test", [])
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'<?xml version="1.0"?><tv></tv>'
        mock_run.return_value = mock_result

        success, content, error = XmltvGrabberService.run_grabber("tv_grab_test", days=3)

        assert success is True
        assert b"<tv>" in content
        assert error == ""

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    @patch("subprocess.run")
    def test_run_grabber_failure(self, mock_run, mock_get_grabber):
        """Test handling grabber failure"""
        mock_get_grabber.return_value = XmltvGrabber("tv_grab_test", "Test", "/usr/bin/tv_grab_test", [])
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"Error: invalid configuration"
        mock_run.return_value = mock_result

        success, content, error = XmltvGrabberService.run_grabber("tv_grab_test")

        assert success is False
        assert content == b""
        assert "invalid configuration" in error

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    @patch("subprocess.run")
    def test_run_grabber_timeout(self, mock_run, mock_get_grabber):
        """Test handling grabber timeout"""
        import subprocess

        mock_get_grabber.return_value = XmltvGrabber("tv_grab_test", "Test", "/usr/bin/tv_grab_test", [])
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=600)

        success, content, error = XmltvGrabberService.run_grabber("tv_grab_test")

        assert success is False
        assert "timed out" in error.lower()

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    def test_get_grabber_channels_not_found(self, mock_get_grabber):
        """Test getting channels from non-existent grabber"""
        mock_get_grabber.return_value = None

        success, channels, error = XmltvGrabberService.get_grabber_channels("nonexistent")

        assert success is False
        assert channels == []
        assert "not found" in error

    @patch.object(XmltvGrabberService, "get_grabber_by_name")
    @patch("subprocess.run")
    def test_get_grabber_channels_success(self, mock_run, mock_get_grabber):
        """Test getting channels successfully"""
        mock_get_grabber.return_value = XmltvGrabber("tv_grab_test", "Test", "/usr/bin/tv_grab_test", [])
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"""<?xml version="1.0"?>
        <tv>
            <channel id="channel1">
                <display-name>Channel One</display-name>
                <icon src="http://example.com/icon.png"/>
            </channel>
            <channel id="channel2">
                <display-name>Channel Two</display-name>
            </channel>
        </tv>"""
        mock_run.return_value = mock_result

        success, channels, error = XmltvGrabberService.get_grabber_channels("tv_grab_test")

        assert success is True
        assert len(channels) == 2
        assert channels[0]["id"] == "channel1"
        assert channels[0]["name"] == "Channel One"
        assert channels[0]["icon_url"] == "http://example.com/icon.png"
        assert channels[1]["id"] == "channel2"
        assert channels[1]["name"] == "Channel Two"


class TestXmltvGrabberServiceTest:
    """Test the test_grabber method"""

    @patch.object(XmltvGrabberService, "get_grabber_channels")
    @patch.object(XmltvGrabberService, "run_grabber")
    def test_test_grabber_success(self, mock_run, mock_channels):
        """Test successful grabber test"""
        mock_channels.return_value = (True, [{"id": "ch1"}, {"id": "ch2"}], "")
        mock_run.return_value = (
            True,
            b"""<?xml version="1.0"?>
            <tv>
                <programme channel="ch1" start="20251222" stop="20251222">
                    <title>Test Program</title>
                </programme>
            </tv>""",
            "",
        )

        result = XmltvGrabberService.test_grabber("tv_grab_test", "config1")

        assert result["success"] is True
        assert result["channels"] == 2
        assert result["programs"] == 1
        assert "successful" in result["message"].lower()

    @patch.object(XmltvGrabberService, "get_grabber_channels")
    def test_test_grabber_channels_fail(self, mock_channels):
        """Test grabber test when channel listing fails"""
        mock_channels.return_value = (False, [], "Could not list channels")

        result = XmltvGrabberService.test_grabber("tv_grab_test")

        assert result["success"] is False
        assert "Could not list channels" in result["message"]

    @patch.object(XmltvGrabberService, "get_grabber_channels")
    @patch.object(XmltvGrabberService, "run_grabber")
    def test_test_grabber_run_fail(self, mock_run, mock_channels):
        """Test grabber test when run fails"""
        mock_channels.return_value = (True, [{"id": "ch1"}], "")
        mock_run.return_value = (False, b"", "Connection error")

        result = XmltvGrabberService.test_grabber("tv_grab_test")

        assert result["success"] is False
        assert "Connection error" in result["message"]


class TestParseChannelList:
    """Test channel list parsing"""

    def test_parse_channel_list_valid(self):
        """Test parsing valid channel list XML"""
        xml = b"""<?xml version="1.0"?>
        <tv>
            <channel id="ABC">
                <display-name>ABC Network</display-name>
                <icon src="http://example.com/abc.png"/>
            </channel>
            <channel id="NBC">
                <display-name>NBC Network</display-name>
            </channel>
        </tv>"""

        channels = XmltvGrabberService._parse_channel_list(xml)

        assert len(channels) == 2
        assert channels[0]["id"] == "ABC"
        assert channels[0]["name"] == "ABC Network"
        assert channels[0]["icon_url"] == "http://example.com/abc.png"
        assert channels[1]["id"] == "NBC"
        assert channels[1]["icon_url"] is None

    def test_parse_channel_list_empty(self):
        """Test parsing empty channel list"""
        xml = b"""<?xml version="1.0"?><tv></tv>"""

        channels = XmltvGrabberService._parse_channel_list(xml)

        assert channels == []

    def test_parse_channel_list_invalid_xml(self):
        """Test parsing invalid XML"""
        xml = b"not valid xml"

        channels = XmltvGrabberService._parse_channel_list(xml)

        assert channels == []

    def test_parse_channel_list_missing_id(self):
        """Test parsing channel without id attribute"""
        xml = b"""<?xml version="1.0"?>
        <tv>
            <channel>
                <display-name>No ID Channel</display-name>
            </channel>
            <channel id="valid">
                <display-name>Valid Channel</display-name>
            </channel>
        </tv>"""

        channels = XmltvGrabberService._parse_channel_list(xml)

        assert len(channels) == 1
        assert channels[0]["id"] == "valid"

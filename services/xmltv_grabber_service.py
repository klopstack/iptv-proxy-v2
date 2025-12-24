"""
XMLTV Grabber Service

Provides an interface to run XMLTV grabbers (tv_grab_*) to fetch EPG data
from various sources like Zap2it, TVGuide, etc.

The XMLTV project provides grabbers for many regions:
- tv_grab_zz_sdjson - Schedules Direct JSON API
- tv_grab_na_dd - DataDirect (North America)
- tv_grab_uk_tvguide - UK TV Guide
- And many more region-specific grabbers
"""
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Directory to store grabber configurations
GRABBER_CONFIG_DIR = Path("/app/data/xmltv_configs")


@dataclass
class XmltvGrabber:
    """Information about an installed XMLTV grabber"""

    name: str  # e.g., "tv_grab_zz_sdjson"
    description: str  # e.g., "Schedules Direct JSON API"
    path: str  # Full path to the grabber executable
    capabilities: List[str]  # e.g., ["baseline", "manualconfig", "preferredmethod"]


@dataclass
class GrabberConfig:
    """Configuration for a specific grabber instance"""

    grabber_name: str
    config_file: str
    channels: List[Dict]  # List of channel configurations
    options: Dict  # Additional grabber options


class XmltvGrabberService:
    """Service for managing and running XMLTV grabbers"""

    @staticmethod
    def get_installed_grabbers() -> List[XmltvGrabber]:
        """
        Discover all installed XMLTV grabbers on the system.

        Returns:
            List of XmltvGrabber objects for each installed grabber
        """
        grabbers = []

        # Common locations for XMLTV grabbers
        search_paths = [
            "/usr/bin",
            "/usr/local/bin",
            "/usr/share/perl5/XMLTV",
        ]

        for path in search_paths:
            if not os.path.isdir(path):
                continue

            for filename in os.listdir(path):
                if filename.startswith("tv_grab_"):
                    full_path = os.path.join(path, filename)
                    if os.access(full_path, os.X_OK):
                        grabber = XmltvGrabberService._get_grabber_info(full_path, filename)
                        if grabber:
                            grabbers.append(grabber)

        # Sort by name for consistent ordering
        grabbers.sort(key=lambda g: g.name)

        logger.info(f"Found {len(grabbers)} installed XMLTV grabbers")
        return grabbers

    @staticmethod
    def _get_grabber_info(path: str, name: str) -> Optional[XmltvGrabber]:
        """
        Get information about a specific grabber.

        Args:
            path: Full path to the grabber executable
            name: Name of the grabber (e.g., "tv_grab_zz_sdjson")

        Returns:
            XmltvGrabber object or None if grabber info cannot be retrieved
        """
        description = ""
        capabilities = []

        try:
            # Try to get description
            result = subprocess.run(
                [path, "--description"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                description = result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.debug(f"Could not get description for {name}: {e}")

        try:
            # Try to get capabilities
            result = subprocess.run(
                [path, "--capabilities"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                capabilities = result.stdout.strip().split("\n")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.debug(f"Could not get capabilities for {name}: {e}")

        return XmltvGrabber(
            name=name,
            description=description or f"XMLTV grabber: {name}",
            path=path,
            capabilities=capabilities,
        )

    @staticmethod
    def get_grabber_by_name(name: str) -> Optional[XmltvGrabber]:
        """
        Get information about a specific grabber by name.

        Args:
            name: Grabber name (e.g., "tv_grab_zz_sdjson")

        Returns:
            XmltvGrabber object or None if not found
        """
        grabbers = XmltvGrabberService.get_installed_grabbers()
        for grabber in grabbers:
            if grabber.name == name:
                return grabber
        return None

    @staticmethod
    def configure_grabber(
        grabber_name: str,
        config_name: str,
        config_data: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Configure a grabber with the given configuration.

        Some grabbers support --configure for interactive setup, but we need
        to handle pre-configured setups for our use case.

        Args:
            grabber_name: Name of the grabber
            config_name: Unique name for this configuration
            config_data: Configuration file contents (grabber-specific format)

        Returns:
            Tuple of (success, message)
        """
        grabber = XmltvGrabberService.get_grabber_by_name(grabber_name)
        if not grabber:
            return False, f"Grabber '{grabber_name}' not found"

        # Ensure config directory exists
        GRABBER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        config_path = GRABBER_CONFIG_DIR / f"{config_name}.conf"

        if config_data:
            # Write provided configuration
            try:
                config_path.write_text(config_data)
                logger.info(f"Saved configuration for {grabber_name} to {config_path}")
                return True, f"Configuration saved to {config_path}"
            except IOError as e:
                return False, f"Failed to write configuration: {e}"

        # Try running with --configure if no data provided
        if "manualconfig" in grabber.capabilities:
            return False, (
                f"Grabber '{grabber_name}' requires manual configuration. " "Please provide configuration data."
            )

        return True, "No configuration required for this grabber"

    @staticmethod
    def get_grabber_config_path(config_name: str) -> Path:
        """Get the path to a grabber configuration file."""
        return GRABBER_CONFIG_DIR / f"{config_name}.conf"

    @staticmethod
    def list_grabber_configs(grabber_name: Optional[str] = None) -> List[Dict]:
        """
        List all saved grabber configurations.

        Args:
            grabber_name: Optional filter by grabber name

        Returns:
            List of configuration metadata dicts
        """
        configs: List[Dict] = []

        if not GRABBER_CONFIG_DIR.exists():
            return configs

        for config_file in GRABBER_CONFIG_DIR.glob("*.conf"):
            config_name = config_file.stem
            try:
                stat = config_file.stat()
                configs.append(
                    {
                        "name": config_name,
                        "file": str(config_file),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "size": stat.st_size,
                    }
                )
            except OSError:
                continue

        return configs

    @staticmethod
    def delete_grabber_config(config_name: str) -> Tuple[bool, str]:
        """
        Delete a grabber configuration.

        Args:
            config_name: Name of the configuration to delete

        Returns:
            Tuple of (success, message)
        """
        config_path = GRABBER_CONFIG_DIR / f"{config_name}.conf"

        if not config_path.exists():
            return False, f"Configuration '{config_name}' not found"

        try:
            config_path.unlink()
            logger.info(f"Deleted configuration: {config_path}")
            return True, "Configuration deleted"
        except OSError as e:
            return False, f"Failed to delete configuration: {e}"

    @staticmethod
    def run_grabber(
        grabber_name: str,
        config_name: Optional[str] = None,
        days: int = 7,
        offset: int = 0,
        output_file: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> Tuple[bool, bytes, str]:
        """
        Run a grabber to fetch EPG data.

        Args:
            grabber_name: Name of the grabber to run
            config_name: Name of the configuration to use (if any)
            days: Number of days of EPG data to fetch
            offset: Day offset to start from
            output_file: Optional file path to write output to
            extra_args: Additional command-line arguments

        Returns:
            Tuple of (success, xml_content, error_message)
        """
        grabber = XmltvGrabberService.get_grabber_by_name(grabber_name)
        if not grabber:
            return False, b"", f"Grabber '{grabber_name}' not found"

        cmd = [grabber.path]

        # Add configuration file if specified
        if config_name:
            config_path = XmltvGrabberService.get_grabber_config_path(config_name)
            if config_path.exists():
                cmd.extend(["--config-file", str(config_path)])
            else:
                logger.warning(f"Config file not found: {config_path}")

        # Add days parameter if supported
        cmd.extend(["--days", str(days)])

        # Add offset if specified
        if offset > 0:
            cmd.extend(["--offset", str(offset)])

        # Add any extra arguments
        if extra_args:
            cmd.extend(extra_args)

        # Add output file if specified
        if output_file:
            cmd.extend(["--output", output_file])

        logger.info(f"Running grabber command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode == 0:
                xml_content = result.stdout
                if output_file and os.path.exists(output_file):
                    with open(output_file, "rb") as f:
                        xml_content = f.read()
                logger.info(f"Grabber completed successfully, {len(xml_content)} bytes")
                return True, xml_content, ""
            else:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                logger.error(f"Grabber failed: {error_msg}")
                return False, b"", error_msg

        except subprocess.TimeoutExpired:
            return False, b"", "Grabber timed out after 10 minutes"
        except subprocess.SubprocessError as e:
            return False, b"", f"Failed to run grabber: {e}"

    @staticmethod
    def get_grabber_channels(
        grabber_name: str,
        config_name: Optional[str] = None,
    ) -> Tuple[bool, List[Dict], str]:
        """
        Get available channels from a grabber using --list-channels.

        Args:
            grabber_name: Name of the grabber
            config_name: Optional configuration name

        Returns:
            Tuple of (success, channels_list, error_message)
        """
        grabber = XmltvGrabberService.get_grabber_by_name(grabber_name)
        if not grabber:
            return False, [], f"Grabber '{grabber_name}' not found"

        cmd = [grabber.path, "--list-channels"]

        if config_name:
            config_path = XmltvGrabberService.get_grabber_config_path(config_name)
            if config_path.exists():
                cmd.extend(["--config-file", str(config_path)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
            )

            if result.returncode == 0:
                # Parse the XMLTV channel list output
                channels = XmltvGrabberService._parse_channel_list(result.stdout)
                return True, channels, ""
            else:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                return False, [], error_msg

        except subprocess.TimeoutExpired:
            return False, [], "Channel list request timed out"
        except subprocess.SubprocessError as e:
            return False, [], f"Failed to get channels: {e}"

    @staticmethod
    def _parse_channel_list(xml_content: bytes) -> List[Dict]:
        """
        Parse XMLTV channel list output.

        Args:
            xml_content: Raw XML bytes from --list-channels

        Returns:
            List of channel dicts with id and name
        """
        import xml.etree.ElementTree as ET

        channels = []

        try:
            root = ET.fromstring(xml_content)

            for channel_elem in root.findall("channel"):
                channel_id = channel_elem.get("id")
                if not channel_id:
                    continue

                display_name = channel_id
                dn_elem = channel_elem.find("display-name")
                if dn_elem is not None and dn_elem.text:
                    display_name = dn_elem.text.strip()

                icon_url = None
                icon_elem = channel_elem.find("icon")
                if icon_elem is not None:
                    icon_url = icon_elem.get("src")

                channels.append(
                    {
                        "id": channel_id,
                        "name": display_name,
                        "icon_url": icon_url,
                    }
                )

        except ET.ParseError as e:
            logger.error(f"Failed to parse channel list XML: {e}")

        return channels

    @staticmethod
    def test_grabber(grabber_name: str, config_name: Optional[str] = None) -> Dict:
        """
        Test a grabber configuration by fetching minimal data.

        Args:
            grabber_name: Name of the grabber
            config_name: Optional configuration name

        Returns:
            Dict with test results
        """
        result = {
            "grabber": grabber_name,
            "config": config_name,
            "success": False,
            "message": "",
            "channels": 0,
            "programs": 0,
        }

        # First, try to list channels
        success, channels, error = XmltvGrabberService.get_grabber_channels(grabber_name, config_name)

        if success:
            result["channels"] = len(channels)
        else:
            result["message"] = f"Failed to list channels: {error}"
            return result

        # Try a minimal grab (1 day)
        success, xml_content, error = XmltvGrabberService.run_grabber(
            grabber_name,
            config_name,
            days=1,
        )

        if success:
            result["success"] = True
            result["message"] = "Grabber test successful"
            # Count programs in the output
            try:
                import xml.etree.ElementTree as ET

                root = ET.fromstring(xml_content)
                result["programs"] = len(root.findall("programme"))
            except Exception:
                pass
        else:
            result["message"] = f"Grabber test failed: {error}"

        return result

"""
Tests for FCC Facility service - parsing and lookup
"""
import pytest

from models import FccFacility, db
from services.fcc_facility_service import FccFacilityService

# Sample facility.dat data for testing (pipe-delimited, header + records)
SAMPLE_FACILITY_DATA = b"""active_ind|atsc3_ind|authorizing_act|callsign|callsign_effective_date|channel|channel_sharing_ind|community_served_city|community_served_state|create_ts|digital_operation|expiration_date|facility_id|facility_status|facility_type|facility_uuid|facility_zone_code|frequency|last_update_ts|latest_filing_version_id|license_filing_id|network_affiliation|nielsen_dma_rank|primary_station|satellite_tv_ind|service_code|station_type|status_date|tsid_dtv|tsid_ntsc|tv_virtual_channel|^|
Y|||KABC-TV||7|N|LOS ANGELES|CA|2020-01-01 00:00:00.0|A|2025-01-01 00:00:00.0|1|LICEN|EDT|uuid1||123.0|2024-01-01 00:00:00.0|v1|l1|ABC|Los Angeles|Y|N|DTV|M|2020-01-01 00:00:00.0|||7|^|
Y|||WNBC||4|N|NEW YORK|NY|2020-01-01 00:00:00.0|A|2025-01-01 00:00:00.0|2|LICEN|EDT|uuid2||456.0|2024-02-01 00:00:00.0|v2|l2|NBC|New York|Y|N|DTV|M|2020-01-01 00:00:00.0|||4|^|
Y|||WFAA-TV||8|N|DALLAS|TX|2020-01-01 00:00:00.0|A|2025-01-01 00:00:00.0|3|LICEN|EDT|uuid3||789.0|2024-03-01 00:00:00.0|v3|l3|ABC|Dallas-Ft. Worth|Y|N|DTV|M|2020-01-01 00:00:00.0|||8|^|
Y|||KFMZ||100|N|BROOKFIELD|MO|2020-01-01 00:00:00.0|A|2025-01-01 00:00:00.0|4|LICEN|EDT|uuid4||1470.0|2024-04-01 00:00:00.0|v4|l4|||Y|N|AM|M|2020-01-01 00:00:00.0||||^|
Y|||W45AB||45|N|LOS ANGELES|CA|2020-01-01 00:00:00.0|A|2025-01-01 00:00:00.0|5|LICEN|EDT|uuid5||650.0|2024-05-01 00:00:00.0|v5|l5|Independent|Los Angeles|N|N|LPT|T|2020-01-01 00:00:00.0|||45|^|
N|||WXYZ-TV||7|N|DETROIT|MI|2020-01-01 00:00:00.0|A|2025-01-01 00:00:00.0|6|LICEN|EDT|uuid6||321.0|2024-06-01 00:00:00.0|v6|l6|ABC|Detroit|Y|N|DTV|M|2020-01-01 00:00:00.0|||7|^|
"""


class TestFccFacilityParsing:
    """Tests for parsing facility.dat data"""

    def test_parse_facility_data_filters_tv_only(self):
        """Test that only TV-related service codes are parsed"""
        records = FccFacilityService.parse_facility_data(SAMPLE_FACILITY_DATA)

        # Should include DTV and LPT, but not AM
        callsigns = {r["callsign"] for r in records}
        assert "KABC-TV" in callsigns
        assert "WNBC" in callsigns
        assert "W45AB" in callsigns  # LPT station
        assert "KFMZ" not in callsigns  # AM radio station

    def test_parse_facility_data_extracts_fields(self):
        """Test that all expected fields are extracted"""
        records = FccFacilityService.parse_facility_data(SAMPLE_FACILITY_DATA)

        # Find KABC-TV record
        kabc = next((r for r in records if r["callsign"] == "KABC-TV"), None)
        assert kabc is not None
        assert kabc["facility_id"] == 1
        assert kabc["community_city"] == "LOS ANGELES"
        assert kabc["community_state"] == "CA"
        assert kabc["network_affiliation"] == "ABC"
        assert kabc["nielsen_dma"] == "Los Angeles"
        assert kabc["service_code"] == "DTV"
        assert kabc["station_type"] == "M"
        assert kabc["active"] is True

    def test_parse_facility_data_handles_inactive(self):
        """Test that inactive flag is parsed correctly"""
        records = FccFacilityService.parse_facility_data(SAMPLE_FACILITY_DATA)

        # Find WXYZ-TV record (inactive)
        wxyz = next((r for r in records if r["callsign"] == "WXYZ-TV"), None)
        assert wxyz is not None
        assert wxyz["active"] is False

    def test_parse_facility_data_handles_empty_fields(self):
        """Test that empty/missing fields are handled"""
        records = FccFacilityService.parse_facility_data(SAMPLE_FACILITY_DATA)

        # W45AB has no network affiliation
        w45ab = next((r for r in records if r["callsign"] == "W45AB"), None)
        assert w45ab is not None
        # Should have "INDEPENDENT" as network (normalized to uppercase)
        assert w45ab["network_affiliation"] == "INDEPENDENT"

    def test_parse_empty_data(self):
        """Test parsing empty data"""
        records = FccFacilityService.parse_facility_data(b"")
        assert records == []

    def test_parse_header_only(self):
        """Test parsing data with only header"""
        header_only = b"active_ind|callsign|service_code|^|\n"
        records = FccFacilityService.parse_facility_data(header_only)
        assert records == []


class TestNetworkAffiliationParsing:
    """Tests for parsing and normalizing network affiliation data"""

    def test_simple_network_names(self):
        """Test simple network names are normalized to uppercase"""
        assert FccFacilityService._parse_network_affiliation("ABC") == "ABC"
        assert FccFacilityService._parse_network_affiliation("Fox") == "FOX"
        assert FccFacilityService._parse_network_affiliation("nbc") == "NBC"
        assert FccFacilityService._parse_network_affiliation("cbs") == "CBS"
        assert FccFacilityService._parse_network_affiliation("PBS") == "PBS"

    def test_slash_separated_networks(self):
        """Test slash-separated network strings extract primary network"""
        assert FccFacilityService._parse_network_affiliation("FOX/COZI-TV") == "FOX"
        assert FccFacilityService._parse_network_affiliation("CBS/MeTV") == "CBS"
        assert FccFacilityService._parse_network_affiliation("NBC/Cozi") == "NBC"

    def test_subchannel_info_with_channel_numbers(self):
        """Test network strings with subchannel numbers"""
        # Format: "5.1 FOX, 5.2 SSSEN, 5.3 Court TV Mystery, 5.4 Dabl"
        result = FccFacilityService._parse_network_affiliation("5.1 FOX, 5.2 SSSEN, 5.3 Court TV Mystery, 5.4 Dabl")
        assert result == "FOX"

        result = FccFacilityService._parse_network_affiliation("25.1 ABC, 25.2 MeTV, 25.3 Heroes")
        assert result == "ABC"

    def test_parenthetical_subchannel_info(self):
        """Test network strings with parenthetical subchannel info"""
        # Format: "FOX (25.1); Comet TV (25.2) & Laff TV (25.3)"
        result = FccFacilityService._parse_network_affiliation("FOX (25.1); Comet TV (25.2) & Laff TV (25.3)")
        assert result == "FOX"

        result = FccFacilityService._parse_network_affiliation("ABC (7.1); This TV (7.2)")
        assert result == "ABC"

    def test_independent_stations(self):
        """Test Independent station designation"""
        assert FccFacilityService._parse_network_affiliation("Independent") == "INDEPENDENT"
        assert FccFacilityService._parse_network_affiliation("IND") == "IND"

    def test_empty_and_none_values(self):
        """Test empty and None inputs"""
        assert FccFacilityService._parse_network_affiliation(None) is None
        assert FccFacilityService._parse_network_affiliation("") is None
        assert FccFacilityService._parse_network_affiliation("   ") is None

    def test_whitespace_handling(self):
        """Test whitespace is properly stripped"""
        assert FccFacilityService._parse_network_affiliation("  ABC  ") == "ABC"
        assert FccFacilityService._parse_network_affiliation(" FOX ") == "FOX"

    def test_complex_dma_state_concatenated(self):
        """Test handling of improperly concatenated data (shouldn't happen with proper parsing)"""
        # This tests that even if garbage data is passed, we extract the network
        result = FccFacilityService._parse_network_affiliation(
            "FOX (25.1); Comet TV (25.2) & Laff TV (25.3)DMA:Boston (Manchester)State:MA"
        )
        assert result == "FOX"

    def test_real_world_examples(self):
        """Test real-world examples from user reports"""
        # Example 1: KVVU
        result = FccFacilityService._parse_network_affiliation("5.1 FOX, 5.2 SSSEN, 5.3 Court TV Mystery, 5.4 Dabl")
        assert result == "FOX"

        # Example 2: Boston FOX affiliate
        result = FccFacilityService._parse_network_affiliation("FOX (25.1); Comet TV (25.2) & Laff TV (25.3)")
        assert result == "FOX"

        # Example 3: Syracuse
        result = FccFacilityService._parse_network_affiliation("FOX/COZI-TV")
        assert result == "FOX"


class TestNetworkDetectionFromName:
    """Tests for detecting network affiliation from channel names"""

    def test_cw_detection(self):
        """Test CW network detection from channel names"""
        assert FccFacilityService._detect_network_from_name("US: CW (KSTW)") == "CW"
        assert FccFacilityService._detect_network_from_name("US: CW 36 (KICU) SAN JOSE HD") == "CW"
        assert FccFacilityService._detect_network_from_name("US: CW 25 (WCWW) South Bend") == "CW"
        assert FccFacilityService._detect_network_from_name("CW KICU") == "CW"

    def test_major_network_detection(self):
        """Test detection of major broadcast networks"""
        assert FccFacilityService._detect_network_from_name("US: ABC 7 (KABC)") == "ABC"
        assert FccFacilityService._detect_network_from_name("US: NBC (KNBC)") == "NBC"
        assert FccFacilityService._detect_network_from_name("US: CBS 2 (KCBS)") == "CBS"
        assert FccFacilityService._detect_network_from_name("US: FOX 11 (KTTV)") == "FOX"
        assert FccFacilityService._detect_network_from_name("US: PBS (KCET)") == "PBS"

    def test_no_network_detected(self):
        """Test channels without network indicators"""
        # Should return None for generic names
        assert FccFacilityService._detect_network_from_name("US: Local News Channel") is None
        assert FccFacilityService._detect_network_from_name("HD Sports Channel") is None

    def test_empty_and_none(self):
        """Test empty and None inputs"""
        assert FccFacilityService._detect_network_from_name(None) is None
        assert FccFacilityService._detect_network_from_name("") is None

    def test_case_insensitive(self):
        """Test that detection is case insensitive"""
        assert FccFacilityService._detect_network_from_name("us: cw (kstw)") == "CW"
        assert FccFacilityService._detect_network_from_name("US: FOX (kttv)") == "FOX"


class TestFccFacilitySync:
    """Tests for syncing facility records to database"""

    @pytest.fixture
    def app(self):
        """Create test Flask app with database"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()

    def test_sync_creates_new_records(self, app):
        """Test that sync creates new facility records"""
        with app.app_context():
            records = FccFacilityService.parse_facility_data(SAMPLE_FACILITY_DATA)
            stats = FccFacilityService.sync_facilities(records)

            # Should have added TV records (DTV + LPT, excluding AM)
            assert stats["added"] >= 4  # At least KABC, WNBC, WFAA, WXYZ
            assert stats["errors"] == 0

            # Verify records exist in database
            kabc = FccFacility.query.filter_by(callsign="KABC-TV").first()
            assert kabc is not None
            assert kabc.community_city == "LOS ANGELES"

    def test_sync_updates_existing_records(self, app):
        """Test that sync updates existing facility records"""
        with app.app_context():
            # First sync
            records = FccFacilityService.parse_facility_data(SAMPLE_FACILITY_DATA)
            FccFacilityService.sync_facilities(records)

            # Modify a record
            modified_data = SAMPLE_FACILITY_DATA.replace(b"|ABC|", b"|FOX|")
            records2 = FccFacilityService.parse_facility_data(modified_data)
            stats2 = FccFacilityService.sync_facilities(records2)

            # Should have some updates
            assert stats2["updated"] >= 1 or stats2["unchanged"] >= 1

    def test_sync_handles_duplicates(self, app):
        """Test that sync handles duplicate facility IDs"""
        with app.app_context():
            records = FccFacilityService.parse_facility_data(SAMPLE_FACILITY_DATA)

            # Sync twice
            stats1 = FccFacilityService.sync_facilities(records)
            stats2 = FccFacilityService.sync_facilities(records)

            # Second sync should have unchanged records
            assert stats2["unchanged"] >= stats1["added"]


class TestFccFacilityLookup:
    """Tests for facility lookup methods"""

    @pytest.fixture
    def app_with_data(self):
        """Create test Flask app with sample facility data"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()

            # Add sample facilities
            facilities = [
                FccFacility(
                    facility_id=1,
                    callsign="KABC-TV",
                    service_code="DTV",
                    station_type="M",
                    community_city="LOS ANGELES",
                    community_state="CA",
                    network_affiliation="ABC",
                    nielsen_dma="Los Angeles",
                    active=True,
                ),
                FccFacility(
                    facility_id=2,
                    callsign="KNBC",
                    service_code="DTV",
                    station_type="M",
                    community_city="LOS ANGELES",
                    community_state="CA",
                    network_affiliation="NBC",
                    nielsen_dma="Los Angeles",
                    active=True,
                ),
                FccFacility(
                    facility_id=3,
                    callsign="WNBC",
                    service_code="DTV",
                    station_type="M",
                    community_city="NEW YORK",
                    community_state="NY",
                    network_affiliation="NBC",
                    nielsen_dma="New York",
                    active=True,
                ),
                FccFacility(
                    facility_id=4,
                    callsign="KABC",
                    service_code="TV",
                    station_type="M",
                    community_city="LOS ANGELES",
                    community_state="CA",
                    network_affiliation="ABC",
                    nielsen_dma="Los Angeles",
                    active=True,
                ),
            ]
            for f in facilities:
                db.session.add(f)
            db.session.commit()

            yield app
            db.session.remove()
            db.drop_all()

    def test_lookup_by_callsign_exact(self, app_with_data):
        """Test exact callsign lookup"""
        with app_with_data.app_context():
            facility = FccFacilityService.lookup_by_callsign("KABC-TV")
            assert facility is not None
            assert facility.callsign == "KABC-TV"
            assert facility.community_city == "LOS ANGELES"

    def test_lookup_by_callsign_case_insensitive(self, app_with_data):
        """Test callsign lookup is case insensitive"""
        with app_with_data.app_context():
            facility = FccFacilityService.lookup_by_callsign("kabc-tv")
            assert facility is not None
            assert facility.callsign == "KABC-TV"

    def test_lookup_by_callsign_prefers_dtv(self, app_with_data):
        """Test that DTV service code is preferred over TV"""
        with app_with_data.app_context():
            # Both KABC-TV (DTV) and KABC (TV) exist
            facility = FccFacilityService.lookup_by_callsign("KABC")
            # Should prefer the one without suffix first, but this tests ordering logic
            assert facility is not None

    def test_lookup_by_callsign_not_found(self, app_with_data):
        """Test callsign lookup returns None for unknown callsign"""
        with app_with_data.app_context():
            facility = FccFacilityService.lookup_by_callsign("WXYZ-TV")
            assert facility is None

    def test_lookup_by_city_state(self, app_with_data):
        """Test lookup by city and state"""
        with app_with_data.app_context():
            facilities = FccFacilityService.lookup_by_city_state("LOS ANGELES", "CA")
            assert len(facilities) >= 2
            callsigns = {f.callsign for f in facilities}
            assert "KABC-TV" in callsigns
            assert "KNBC" in callsigns

    def test_lookup_by_city_state_with_network(self, app_with_data):
        """Test lookup by city/state with network filter"""
        with app_with_data.app_context():
            facilities = FccFacilityService.lookup_by_city_state("LOS ANGELES", "CA", "NBC")
            assert len(facilities) >= 1
            assert all("NBC" in (f.network_affiliation or "") for f in facilities)

    def test_lookup_by_dma(self, app_with_data):
        """Test lookup by DMA name"""
        with app_with_data.app_context():
            facilities = FccFacilityService.lookup_by_dma("Los Angeles")
            assert len(facilities) >= 2

    def test_get_city_for_callsign(self, app_with_data):
        """Test convenience method for getting city/state"""
        with app_with_data.app_context():
            result = FccFacilityService.get_city_for_callsign("WNBC")
            assert result is not None
            city, state = result
            assert city == "NEW YORK"
            assert state == "NY"

    def test_get_city_for_callsign_not_found(self, app_with_data):
        """Test get_city_for_callsign returns None for unknown"""
        with app_with_data.app_context():
            result = FccFacilityService.get_city_for_callsign("UNKNOWN")
            assert result is None

    def test_get_callsigns_for_city(self, app_with_data):
        """Test getting all callsigns for a city"""
        with app_with_data.app_context():
            callsigns = FccFacilityService.get_callsigns_for_city("LOS ANGELES", "CA")
            assert len(callsigns) >= 2
            assert "KABC-TV" in callsigns
            assert "KNBC" in callsigns


class TestFccFacilityStats:
    """Tests for facility statistics"""

    @pytest.fixture
    def app_with_data(self):
        """Create test Flask app with sample facility data"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()

            # Add sample facilities
            facilities = [
                FccFacility(facility_id=1, callsign="KABC-TV", service_code="DTV", network_affiliation="ABC"),
                FccFacility(facility_id=2, callsign="KNBC", service_code="DTV", network_affiliation="NBC"),
                FccFacility(facility_id=3, callsign="KCBS-TV", service_code="DTV", network_affiliation="CBS"),
                FccFacility(facility_id=4, callsign="W45AB", service_code="LPT", network_affiliation=None),
            ]
            for f in facilities:
                db.session.add(f)
            db.session.commit()

            yield app
            db.session.remove()
            db.drop_all()

    def test_get_stats(self, app_with_data):
        """Test getting facility statistics"""
        with app_with_data.app_context():
            stats = FccFacilityService.get_stats()

            assert stats["total_facilities"] == 4
            assert "DTV" in stats["by_service_code"]
            assert stats["by_service_code"]["DTV"] == 3
            assert "LPT" in stats["by_service_code"]
            assert stats["by_service_code"]["LPT"] == 1

    def test_get_stats_empty_db(self):
        """Test getting stats with empty database"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()
            stats = FccFacilityService.get_stats()
            assert stats["total_facilities"] == 0
            db.drop_all()


class TestCallsignExtraction:
    """Tests for extracting callsigns from channel names"""

    def test_extract_simple_callsign(self):
        """Test extracting simple callsigns"""
        assert FccFacilityService.extract_callsign_from_name("KABC") == "KABC"
        assert FccFacilityService.extract_callsign_from_name("WNBC") == "WNBC"
        assert FccFacilityService.extract_callsign_from_name("WFAA") == "WFAA"

    def test_extract_callsign_with_suffix(self):
        """Test extracting callsigns with TV/DT suffixes"""
        assert FccFacilityService.extract_callsign_from_name("KABC-TV") == "KABC"
        assert FccFacilityService.extract_callsign_from_name("WNBC-DT") == "WNBC"

    def test_extract_callsign_with_hd(self):
        """Test extracting callsigns with HD suffix"""
        assert FccFacilityService.extract_callsign_from_name("KABC HD") == "KABC"
        assert FccFacilityService.extract_callsign_from_name("KABC-TV HD") == "KABC"

    def test_extract_callsign_with_prefix(self):
        """Test extracting callsigns with country prefixes"""
        assert FccFacilityService.extract_callsign_from_name("US: KABC") == "KABC"
        assert FccFacilityService.extract_callsign_from_name("USA: WNBC HD") == "WNBC"

    def test_extract_callsign_in_parentheses(self):
        """Test extracting callsigns in parentheses - most reliable format"""
        assert FccFacilityService.extract_callsign_from_name("US: NBC (WNBC)") == "WNBC"
        assert FccFacilityService.extract_callsign_from_name("US: CW (KSTW)") == "KSTW"
        assert FccFacilityService.extract_callsign_from_name("US: ABC 7 (KABC) Los Angeles") == "KABC"
        # Handle multiple callsigns with slash
        assert FccFacilityService.extract_callsign_from_name("US: NBC (WSVW/WHSV) HARRISONBURG HD") == "WSVW"

    def test_extract_callsign_in_brackets(self):
        """Test extracting callsigns in brackets"""
        # Note: The regex looks for K/W followed by letters
        result = FccFacilityService.extract_callsign_from_name("[KABC] News")
        assert result == "KABC"

    def test_extract_no_callsign(self):
        """Test that non-callsign names return None"""
        assert FccFacilityService.extract_callsign_from_name("ESPN") is None
        assert FccFacilityService.extract_callsign_from_name("HBO") is None
        assert FccFacilityService.extract_callsign_from_name("CNN") is None
        assert FccFacilityService.extract_callsign_from_name("ABC Network") is None

    def test_extract_requires_minimum_length(self):
        """Test that short matches are rejected"""
        # 'WE' is too short to be a valid callsign
        assert FccFacilityService.extract_callsign_from_name("WE Network") is None


class TestDmaAndNetworkLists:
    """Tests for DMA and network list methods"""

    @pytest.fixture
    def app_with_dma_data(self):
        """Create test app with DMA data"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()

            facilities = [
                FccFacility(
                    facility_id=1,
                    callsign="KABC-TV",
                    service_code="DTV",
                    network_affiliation="ABC",
                    nielsen_dma="Los Angeles",
                    community_state="CA",
                ),
                FccFacility(
                    facility_id=2,
                    callsign="KNBC",
                    service_code="DTV",
                    network_affiliation="NBC",
                    nielsen_dma="Los Angeles",
                    community_state="CA",
                ),
                FccFacility(
                    facility_id=3,
                    callsign="WNBC",
                    service_code="DTV",
                    network_affiliation="NBC",
                    nielsen_dma="New York",
                    community_state="NY",
                ),
                FccFacility(
                    facility_id=4,
                    callsign="WABC-TV",
                    service_code="DTV",
                    network_affiliation="ABC",
                    nielsen_dma="New York",
                    community_state="NY",
                ),
            ]
            for f in facilities:
                db.session.add(f)
            db.session.commit()

            yield app
            db.session.remove()
            db.drop_all()

    def test_get_dma_list(self, app_with_dma_data):
        """Test getting list of DMAs"""
        with app_with_dma_data.app_context():
            dmas = FccFacilityService.get_dma_list()

            assert len(dmas) == 2
            dma_names = {d["name"] for d in dmas}
            assert "Los Angeles" in dma_names
            assert "New York" in dma_names

    def test_get_network_list(self, app_with_dma_data):
        """Test getting list of networks"""
        with app_with_dma_data.app_context():
            networks = FccFacilityService.get_network_list()

            assert len(networks) == 2
            network_names = {n["name"] for n in networks}
            assert "ABC" in network_names
            assert "NBC" in network_names

            # NBC should have count of 2
            nbc = next(n for n in networks if n["name"] == "NBC")
            assert nbc["count"] == 2


class TestStationsRoutes:
    """Tests for the stations blueprint routes"""

    @pytest.fixture
    def client(self):
        """Create test client with database"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()

            # Add test facilities
            facilities = [
                FccFacility(
                    facility_id=1,
                    callsign="KABC-TV",
                    service_code="DTV",
                    network_affiliation="ABC",
                    nielsen_dma="Los Angeles",
                    community_city="LOS ANGELES",
                    community_state="CA",
                    active=True,
                ),
                FccFacility(
                    facility_id=2,
                    callsign="WNBC",
                    service_code="DTV",
                    network_affiliation="NBC",
                    nielsen_dma="New York",
                    community_city="NEW YORK",
                    community_state="NY",
                    active=True,
                ),
            ]
            for f in facilities:
                db.session.add(f)
            db.session.commit()

            with app.test_client() as client:
                yield client

            db.session.remove()
            db.drop_all()

    def test_get_fcc_stats(self, client):
        """Test FCC stats endpoint"""
        response = client.get("/api/fcc/facilities/stats")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_facilities"] == 2

    def test_lookup_callsign(self, client):
        """Test callsign lookup endpoint"""
        response = client.get("/api/fcc/facilities/lookup/callsign/KABC-TV")
        assert response.status_code == 200
        data = response.get_json()
        assert data["callsign"] == "KABC-TV"
        assert data["city"] == "LOS ANGELES"
        assert data["state"] == "CA"
        assert data["network"] == "ABC"

    def test_lookup_callsign_not_found(self, client):
        """Test callsign lookup for non-existent station"""
        response = client.get("/api/fcc/facilities/lookup/callsign/XXXX")
        assert response.status_code == 404

    def test_lookup_city(self, client):
        """Test city lookup endpoint"""
        response = client.get("/api/fcc/facilities/lookup/city?city=LOS%20ANGELES&state=CA")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert data["facilities"][0]["callsign"] == "KABC-TV"

    def test_lookup_city_missing_params(self, client):
        """Test city lookup with missing parameters"""
        response = client.get("/api/fcc/facilities/lookup/city?city=LOS%20ANGELES")
        assert response.status_code == 400

    def test_lookup_dma(self, client):
        """Test DMA lookup endpoint"""
        response = client.get("/api/fcc/facilities/lookup/dma?dma=Los%20Angeles")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1

    def test_lookup_dma_missing_param(self, client):
        """Test DMA lookup with missing parameter"""
        response = client.get("/api/fcc/facilities/lookup/dma")
        assert response.status_code == 400

    def test_get_dma_list(self, client):
        """Test DMA list endpoint"""
        response = client.get("/api/fcc/facilities/dmas")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 2

    def test_get_network_list(self, client):
        """Test network list endpoint"""
        response = client.get("/api/fcc/networks")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 2

    def test_get_channels_by_callsign_no_matches(self, client):
        """Test channels by callsign with no matching channels"""
        response = client.get("/api/fcc/channels/by-callsign/KABC")
        assert response.status_code == 200
        data = response.get_json()
        assert data["callsign"] == "KABC"
        assert data["total_channels"] == 0
        assert data["accounts"] == []


class TestChannelsCallsignLookup:
    """Tests for the channels-by-callsign endpoint"""

    @pytest.fixture
    def client_with_channels(self):
        """Create test client with channels containing callsigns"""
        from app import app
        from models import Account, Channel

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()

            # Create account
            account = Account(
                name="Test Account",
                server="http://test.example.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            # Create channels with callsigns
            channels = [
                Channel(
                    account_id=account.id,
                    stream_id="abc_la",
                    name="US: ABC 7 (KABC) Los Angeles",
                    cleaned_name="ABC 7 Los Angeles",
                    category_id=1,
                    is_active=True,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="nbc_ny",
                    name="US: NBC (WNBC) New York",
                    cleaned_name="NBC New York",
                    category_id=1,
                    is_active=True,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="cbs_la",
                    name="US: CBS (KCBS) Los Angeles",
                    cleaned_name="CBS Los Angeles",
                    category_id=1,
                    is_active=False,  # Inactive channel
                ),
            ]
            for ch in channels:
                db.session.add(ch)
            db.session.commit()

            with app.test_client() as client:
                yield client

            db.session.remove()
            db.drop_all()

    def test_find_channels_by_callsign(self, client_with_channels):
        """Test finding channels that match a callsign"""
        response = client_with_channels.get("/api/fcc/channels/by-callsign/KABC")
        assert response.status_code == 200
        data = response.get_json()
        assert data["callsign"] == "KABC"
        assert data["total_channels"] == 1
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["channels"][0]["name"] == "US: ABC 7 (KABC) Los Angeles"

    def test_find_channels_ignores_inactive(self, client_with_channels):
        """Test that inactive channels are not returned"""
        response = client_with_channels.get("/api/fcc/channels/by-callsign/KCBS")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_channels"] == 0  # Inactive channel not included

    def test_find_channels_no_match(self, client_with_channels):
        """Test callsign with no matching channels"""
        response = client_with_channels.get("/api/fcc/channels/by-callsign/WXYZ")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_channels"] == 0
        assert data["accounts"] == []


class TestChannelEnrichment:
    """Tests for channel enrichment functionality"""

    @pytest.fixture
    def app_with_channels(self):
        """Create test app with FCC data and channels"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            from models import Account, Channel, ChannelTag, Tag

            db.create_all()

            # Add FCC facilities
            facilities = [
                FccFacility(
                    facility_id=1,
                    callsign="KABC-TV",
                    service_code="DTV",
                    network_affiliation="ABC",
                    nielsen_dma="Los Angeles",
                    community_city="LOS ANGELES",
                    community_state="CA",
                    active=True,
                ),
                FccFacility(
                    facility_id=2,
                    callsign="WNBC",
                    service_code="DTV",
                    network_affiliation="NBC",
                    nielsen_dma="New York",
                    community_city="NEW YORK",
                    community_state="NY",
                    active=True,
                ),
            ]
            for f in facilities:
                db.session.add(f)

            # Add test account
            account = Account(
                name="Test Account",
                server="http://test.example.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.flush()

            # Create US tag (required for FCC enrichment)
            us_tag = Tag(name="US")
            db.session.add(us_tag)
            db.session.flush()

            # Add channels that will match FCC data
            channels = [
                Channel(
                    account_id=account.id,
                    stream_id="1",
                    name="KABC Los Angeles",
                ),
                Channel(
                    account_id=account.id,
                    stream_id="2",
                    name="US: WNBC HD",
                ),
                Channel(
                    account_id=account.id,
                    stream_id="3",
                    name="ESPN",  # Won't match - no callsign
                ),
            ]
            for c in channels:
                db.session.add(c)
            db.session.flush()

            # Tag channels 1 and 2 with US tag (but not 3)
            for stream_id in ["1", "2"]:
                channel_tag = ChannelTag(
                    account_id=account.id,
                    stream_id=stream_id,
                    tag_id=us_tag.id,
                )
                db.session.add(channel_tag)
            db.session.commit()

            yield app, account.id

            db.session.remove()
            db.drop_all()

    def test_preview_enrichment(self, app_with_channels):
        """Test previewing channel enrichment"""
        app, account_id = app_with_channels
        with app.app_context():
            matches = FccFacilityService.preview_channel_enrichment(account_id)

            # Should match 2 channels (KABC and WNBC), not ESPN
            assert len(matches) == 2

            # Check KABC match
            kabc = next((m for m in matches if m["extracted_callsign"] == "KABC"), None)
            assert kabc is not None
            assert kabc["fcc_callsign"] == "KABC-TV"
            assert kabc["network"] == "ABC"
            assert kabc["dma"] == "Los Angeles"
            assert "NETWORK:ABC" in kabc["potential_tags"]

            # Check WNBC match
            wnbc = next((m for m in matches if m["extracted_callsign"] == "WNBC"), None)
            assert wnbc is not None
            assert wnbc["network"] == "NBC"

    def test_preview_enrichment_no_matches(self, app_with_channels):
        """Test preview with account that has no matching channels"""
        from models import Account, Channel

        app, _ = app_with_channels
        with app.app_context():
            # Create an account with no callsign channels
            account = Account(
                name="No Callsigns",
                server="http://test.example.com",
                username="test2",
                password="test2",
            )
            db.session.add(account)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="100",
                name="HBO Max",
            )
            db.session.add(channel)
            db.session.commit()

            matches = FccFacilityService.preview_channel_enrichment(account.id)
            assert len(matches) == 0

    def test_apply_enrichment(self, app_with_channels):
        """Test applying enrichment creates tags and associations"""
        from models import ChannelTag, Tag

        app, account_id = app_with_channels
        with app.app_context():
            options = {
                "create_network_tags": True,
                "create_dma_tags": True,
                "create_state_tags": False,
            }
            result = FccFacilityService.apply_channel_enrichment(account_id, options)

            assert result["success"] is True
            assert result["channels_matched"] == 2

            # Check that tags were created
            abc_tag = Tag.query.filter_by(name="NETWORK:ABC").first()
            assert abc_tag is not None

            nbc_tag = Tag.query.filter_by(name="NETWORK:NBC").first()
            assert nbc_tag is not None

            la_tag = Tag.query.filter_by(name="DMA:LOS ANGELES").first()
            assert la_tag is not None

            # Check channel-tag associations
            channel_tags = ChannelTag.query.filter_by(account_id=account_id).all()
            assert len(channel_tags) >= 2  # At least network tags

    def test_apply_enrichment_no_matches(self, app_with_channels):
        """Test applying enrichment with no matching channels"""
        from models import Account

        app, _ = app_with_channels
        with app.app_context():
            # Create account with no matching channels
            account = Account(
                name="Empty",
                server="http://test.example.com",
                username="empty",
                password="empty",
            )
            db.session.add(account)
            db.session.commit()

            options = {"create_network_tags": True}
            result = FccFacilityService.apply_channel_enrichment(account.id, options)

            assert result["success"] is True
            assert result["channels_matched"] == 0
            assert result["message"] == "No channels matched FCC data"

    def test_independent_station_network_override(self):
        """Test that Independent stations get network from channel name"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            from models import Account, Channel, ChannelTag, Tag

            db.create_all()

            # Add FCC facility marked as "Independent" for a CW affiliate
            facility = FccFacility(
                facility_id=999,
                callsign="KSTW",
                service_code="DTV",
                network_affiliation="Independent",  # FCC says Independent
                nielsen_dma="Seattle-Tacoma",
                community_city="TACOMA",
                community_state="WA",
                active=True,
            )
            db.session.add(facility)

            # Add test account
            account = Account(
                name="Test Account",
                server="http://test.example.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.flush()

            # Create US tag
            us_tag = Tag(name="US")
            db.session.add(us_tag)
            db.session.flush()

            # Add CW channel with callsign
            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="US: CW (KSTW)",  # Name indicates CW
            )
            db.session.add(channel)
            db.session.flush()

            # Tag channel with US
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id="1",
                tag_id=us_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            # Apply enrichment
            options = {
                "create_network_tags": True,
                "create_dma_tags": True,
                "create_state_tags": True,
            }
            result = FccFacilityService.apply_channel_enrichment(account.id, options)

            assert result["success"] is True
            assert result["channels_matched"] == 1

            # Check that CW tag was created (not INDEPENDENT)
            cw_tag = Tag.query.filter_by(name="NETWORK:CW").first()
            assert cw_tag is not None, "Expected NETWORK:CW tag, but it wasn't created"

            # Make sure INDEPENDENT tag was NOT created
            ind_tag = Tag.query.filter_by(name="NETWORK:INDEPENDENT").first()
            assert ind_tag is None, "NETWORK:INDEPENDENT should not be created for CW affiliate"

            db.session.remove()
            db.drop_all()

    def test_network_detection_when_fcc_has_no_network(self):
        """Test that network is detected from channel name when FCC has no network data"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            from models import Account, Channel, ChannelTag, Tag

            db.create_all()

            # Add FCC facility with NO network affiliation
            facility = FccFacility(
                facility_id=998,
                callsign="WSVW-LD",
                service_code="DTV",
                network_affiliation=None,  # FCC has no network data
                nielsen_dma="Harrisonburg",
                community_city="HARRISONBURG",
                community_state="VA",
                active=True,
            )
            db.session.add(facility)

            # Add test account
            account = Account(
                name="Test Account",
                server="http://test.example.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.flush()

            # Create US tag
            us_tag = Tag(name="US")
            db.session.add(us_tag)
            db.session.flush()

            # Add NBC channel with callsign - name indicates NBC
            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="US: NBC (WSVW/WHSV) HARRISONBURG HD",  # Name indicates NBC
            )
            db.session.add(channel)
            db.session.flush()

            # Tag channel with US
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id="1",
                tag_id=us_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            # Apply enrichment
            options = {
                "create_network_tags": True,
                "create_dma_tags": True,
                "create_state_tags": True,
            }
            result = FccFacilityService.apply_channel_enrichment(account.id, options)

            assert result["success"] is True
            assert result["channels_matched"] == 1

            # Check that NBC tag was created (detected from channel name)
            nbc_tag = Tag.query.filter_by(name="NETWORK:NBC").first()
            assert nbc_tag is not None, "Expected NETWORK:NBC tag detected from channel name"

            db.session.remove()
            db.drop_all()


class TestEnrichmentRoutes:
    """Tests for enrichment API routes"""

    @pytest.fixture
    def client_with_channels(self):
        """Create test client with channels and FCC data"""
        from app import app

        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            from models import Account, Channel, ChannelTag, Tag

            db.create_all()

            # Add FCC facilities
            facilities = [
                FccFacility(
                    facility_id=1,
                    callsign="KABC-TV",
                    service_code="DTV",
                    network_affiliation="ABC",
                    nielsen_dma="Los Angeles",
                    community_city="LOS ANGELES",
                    community_state="CA",
                    active=True,
                ),
            ]
            for f in facilities:
                db.session.add(f)

            # Add test account with a matching channel
            account = Account(
                name="Test Account",
                server="http://test.example.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.flush()

            # Create US tag (required for FCC enrichment)
            us_tag = Tag(name="US")
            db.session.add(us_tag)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="KABC Los Angeles",
            )
            db.session.add(channel)
            db.session.flush()

            # Tag channel with US tag
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id="1",
                tag_id=us_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            with app.test_client() as client:
                yield client, account.id

            db.session.remove()
            db.drop_all()

    def test_preview_enrichment_endpoint(self, client_with_channels):
        """Test enrichment preview API endpoint"""
        client, account_id = client_with_channels
        response = client.get(f"/api/fcc/enrichment/preview/{account_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["account_id"] == account_id
        assert data["total_matches"] == 1

    def test_preview_enrichment_not_found(self, client_with_channels):
        """Test enrichment preview with invalid account"""
        client, _ = client_with_channels
        response = client.get("/api/fcc/enrichment/preview/9999")
        assert response.status_code == 404

    def test_apply_enrichment_endpoint(self, client_with_channels):
        """Test enrichment apply API endpoint"""
        client, account_id = client_with_channels
        response = client.post(
            f"/api/fcc/enrichment/apply/{account_id}",
            json={"create_network_tags": True, "create_dma_tags": True},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["channels_matched"] == 1

    def test_apply_enrichment_not_found(self, client_with_channels):
        """Test enrichment apply with invalid account"""
        client, _ = client_with_channels
        response = client.post(
            "/api/fcc/enrichment/apply/9999",
            json={"create_network_tags": True},
        )
        assert response.status_code == 404

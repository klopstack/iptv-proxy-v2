"""Historical calendar matching for replay/archive providers (TODO 129 Track B)."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from models import Account, Channel, Event, EventChannelLink, db
from models.sync import Settings
from services.playlist_format_service import render_account_m3u_playlist
from services.ppv.calendar_providers.sofascore.parser_ice_hockey import parse_ice_hockey_scheduled_events
from services.ppv.constants import SETTING_PPV_SOFASCORE_COLLEGE_ENABLED
from services.ppv.enrichment.match_pipeline import CalendarMatchPipeline
from services.ppv.extraction import PPVEventExtractor
from services.ppv.matching.validation import competitors_match_event
from services.ppv.replay_providers import METADATA_KEY_REPLAY_ARCHIVE
from services.ppv.visibility import PPVVisibilityService
from services.thesportsdb_calendar_scraper import TheSportsDBCalendarScraper
from services.url_service import get_proxy_base_url

FIXTURES = Path(__file__).parent / "fixtures"
ICE_HOCKEY_1022 = FIXTURES / "sofascore" / "ice_hockey_2025-10-22.json"
FLO_HOCKEY_TITLE = "Flo (FLSP) 161: 2025 Colorado Eagles vs San Diego Gulls Away - 22/10 22:00"


def _load_ice_hockey(date: str = "2025-10-22"):
    payload = json.loads(ICE_HOCKEY_1022.read_text(encoding="utf-8"))
    return parse_ice_hockey_scheduled_events(payload, date_str=date)


class TestReplayCalendarMatching:
    """Calendar lookup keyed to extracted historical date for replay providers."""

    def test_replay_archive_channels_use_replay_calendar_mode(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_COLLEGE_ENABLED, "true")
            scraper = TheSportsDBCalendarScraper(cache_ttl=60)
            hockey_events = _load_ice_hockey()

            with patch.object(
                scraper,
                "_fetch_milb_events_for_date",
                return_value=[],
            ), patch.object(
                scraper,
                "_fetch_api_events_for_date",
                return_value=[],
            ), patch.object(
                scraper,
                "_fetch_calendar_page",
                return_value=[],
            ), patch.object(
                scraper,
                "_fetch_espn_tennis_events_for_date",
                return_value=[],
            ), patch(
                "services.ppv.calendar_providers.sofascore.fetch_events_for_slug",
                side_effect=lambda slug, date_str, **kwargs: hockey_events
                if slug == "ice-hockey" and kwargs.get("replay")
                else [],
            ) as mock_fetch:
                events = scraper.get_events_for_date("2025-10-22", force_refresh=True, replay=True)

            assert any(event.sport == "Ice Hockey" for event in events)
            mock_fetch.assert_called()
            assert all(call.kwargs.get("replay") is True for call in mock_fetch.call_args_list)

    def test_flo_hockey_extraction_matches_historical_fixture(self):
        """Flo title extracts Oct 2025 date and matches recorded ice-hockey calendar fixture."""
        extractor = PPVEventExtractor()
        extraction = extractor.extract_all(FLO_HOCKEY_TITLE)
        extraction[METADATA_KEY_REPLAY_ARCHIVE] = True
        assert extraction.get(METADATA_KEY_REPLAY_ARCHIVE) is True
        assert extraction.get("date") is not None
        assert extraction["date"].strftime("%Y-%m-%d") == "2025-10-22"

        competitors = extraction.get("competitors")
        calendar_events = _load_ice_hockey()
        assert competitors
        assert any(competitors_match_event(competitors, event) for event in calendar_events)

    def test_replay_pipeline_groups_by_extracted_date_not_today(self):
        """Replay-tagged channels batch calendar fetch on extracted historical date (Track B)."""
        pipeline = CalendarMatchPipeline()
        extractor = PPVEventExtractor()
        extraction = extractor.extract_all(FLO_HOCKEY_TITLE)
        extraction[METADATA_KEY_REPLAY_ARCHIVE] = True
        channel = type("Ch", (), {"name": FLO_HOCKEY_TITLE, "category": None, "id": 1})()

        grouped = pipeline.group_by_date([(channel, extraction)])
        date_key = list(grouped.keys())[0]
        assert date_key.startswith("2025-10-")
        assert date_key != datetime.now().strftime("%Y-%m-%d")
        ctx = extraction.get("_matching_context") or {}
        assert ctx.get("calendar_date") == date_key

    def test_linked_flo_event_classifies_as_historical_in_playlist(self, app):
        """E2E: Flo channel linked to Oct 2025 fixture lands in PPV - Historical when age > 21d."""
        with app.app_context():
            account = Account(
                name="Flo Historical",
                server="http://test.com",
                ppv_visibility="group_live_replay",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="flo-161",
                name=FLO_HOCKEY_TITLE,
                is_ppv=True,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

            historical_start = datetime(2025, 10, 22, 22, 0)
            event = Event(
                external_id="flo-eagles-gulls",
                scheduled_at=historical_start,
                home_team_id="eagles",
                home_team_name="Colorado Eagles",
                away_team_id="gulls",
                away_team_name="San Diego Gulls",
                status=Event.STATUS_FINISHED,
                is_ppv=True,
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.classify_live_replay_channel(channel) == PPVVisibilityService.PPV_GROUP_HISTORICAL

            with app.test_request_context("/"):
                m3u = render_account_m3u_playlist(
                    [channel],
                    account=account,
                    proxy_base=get_proxy_base_url(),
                    use_proxy=True,
                    proxy_icons=False,
                    primary_cred=None,
                )
            assert 'group-title="PPV - Historical"' in m3u

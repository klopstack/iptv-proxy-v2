"""Tests for PPV enrichment channel preview listing."""

from datetime import datetime, timedelta, timezone

from models import Account, Channel, Event, EventChannelLink, db
from services.ppv.preview import list_ppv_enrichment_channels


class TestListPpvEnrichmentChannels:
    def test_filters_by_status_and_includes_linked_event(self, app):
        with app.app_context():
            account = Account(name="Preview", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            matched = Channel(
                account_id=account.id,
                stream_id="p1",
                name="UFC 300: Jones vs Miocic",
                is_ppv=True,
                ppv_enrichment_status="matched",
            )
            queued = Channel(
                account_id=account.id,
                stream_id="p2",
                name="PPV 1",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add_all([matched, queued])
            db.session.commit()

            future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
            event = Event(
                external_id="preview-evt",
                scheduled_at=future,
                home_team_id="j",
                home_team_name="Jones",
                away_team_id="m",
                away_team_name="Miocic",
                league_name="UFC",
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=matched.id))
            db.session.commit()

            result = list_ppv_enrichment_channels(account_id=account.id, status="matched")
            assert result["pagination"]["total"] == 1
            row = result["channels"][0]
            assert row["channel_id"] == matched.id
            assert row["linked_event"] is not None
            assert row["linked_event"]["home_team"] == "Jones"

    def test_search_filters_channel_names(self, app):
        with app.app_context():
            account = Account(name="SearchAcc", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            db.session.add_all(
                [
                    Channel(
                        account_id=account.id,
                        stream_id="s1",
                        name="BOXING: Fury vs Joshua",
                        is_ppv=True,
                        ppv_enrichment_status="no_match",
                    ),
                    Channel(
                        account_id=account.id,
                        stream_id="s2",
                        name="NBA Finals",
                        is_ppv=True,
                        ppv_enrichment_status="no_match",
                    ),
                ]
            )
            db.session.commit()

            result = list_ppv_enrichment_channels(account_id=account.id, search="Fury")
            assert result["pagination"]["total"] == 1
            assert "Fury" in result["channels"][0]["channel_name"]

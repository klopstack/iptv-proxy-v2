# Multi-Account Aggregation

When your provider supplies **separate accounts** (not one account with multiple streams), use:

## Playlist configs

`PlaylistConfig.include_accounts` / `exclude_accounts` JSON arrays select which upstream accounts feed a combined playlist.

Tag filters (`include_tags`, `exclude_tags`, `tag_match_mode`) apply across the merged channel list.

## Xtream credentials

Point an `XtreamCredential` at a `playlist_config_id` so TiviMate sees one unified line-up.

## Channel selection

All outputs use `ChannelQueryService` so M3U, Xtream live, preview, and PPV visibility stay consistent.

## Streaming

Each channel retains its `account_id`; the stream proxy selects upstream credentials for that account when opening `/stream/...`.

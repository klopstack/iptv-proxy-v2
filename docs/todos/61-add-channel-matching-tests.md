# Add unit tests for PPV channel matching context

**Status:** 🔄 In review (PR #19)  
**Priority:** P1  
**Audit:** PPV audit, June 2026

## Problem

`services/ppv/channel_matching.py` builds the UTC calendar-day grouping context used before reverse matching. It handles timezone inference, metadata-only channels, US/EU date boundaries, and MiLB-specific paths.

This module has **no direct tests** — only indirect coverage when enrichment tests mock the entire matching stack.

Incorrect day grouping causes systematic no-match failures that are hard to diagnose in production.

## Affected files

- New: `tests/ppv/test_channel_matching.py`
- `services/ppv/channel_matching.py`
- `tests/test_ppv_timezone_resolution.py` — related but does not cover grouping

## Proposed solution

Table-driven tests for `build_channel_matching_context` (and related helpers):

1. Channel with explicit date in name → correct UTC day bucket.
2. US evening game → correct calendar day vs UTC midnight boundary.
3. Metadata-only / time-only channels.
4. MiLB channel names with league hints.
5. Multi-channel batch → shared date cache behavior.

Use fixed reference datetimes (`freezegun` or injectable clock) for determinism.

## Acceptance criteria

- [x] At least 10 parametrized cases covering timezone edge cases.
- [x] Failures produce actionable assertion messages (channel name, expected date, got date).

## Completion

- PR #19 — https://github.com/klopstack/iptv-proxy-v2/pull/19

## Test plan

Self-contained.

## Dependencies

None.

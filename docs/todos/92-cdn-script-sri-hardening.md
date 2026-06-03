# CDN script Subresource Integrity (SRI)

**Status:** ✅ Done — completed in [98-fcc-patterns-split-and-cdn-sri.md](./98-fcc-patterns-split-and-cdn-sri.md)  
**Priority:** P3  
**Deferred from:** [84-docker-and-secrets-hardening.md](./84-docker-and-secrets-hardening.md) (June 2026)

## Problem

`templates/base.html` loads Bootstrap and related scripts from jsDelivr without `integrity` attributes. A compromised CDN could serve malicious JS to authenticated admin users (behind Authentik).

## Proposed solution

1. Pin CDN URLs to specific versions already in use
2. Add `integrity` and `crossorigin="anonymous"` attributes
3. Prefer vendoring critical admin JS into `static/` where practical

## Acceptance criteria

- [x] All external `<script>` / `<link>` tags in admin templates have SRI or are self-hosted
- [x] Document CDN update procedure when bumping versions

## Dependencies

- [83-xss-audit-legacy-frontend.md](./83-xss-audit-legacy-frontend.md) — related frontend safety track

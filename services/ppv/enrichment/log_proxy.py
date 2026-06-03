"""Lazy logger proxy so tests patching services.ppv.enrichment.logger take effect."""


class _LoggerProxy:
    def __getattr__(self, name):
        import services.ppv.enrichment as enrichment

        return getattr(enrichment.logger, name)


logger = _LoggerProxy()

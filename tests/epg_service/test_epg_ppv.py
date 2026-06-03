"""PPV detection behavior tests live in tests.ppv.test_detection (TODO 64)."""


def test_ppv_detection_helpers_importable():
    from services.ppv.detection import get_ppv_event_title, is_ppv_category, is_ppv_channel, is_ppv_placeholder_name

    assert callable(is_ppv_category)
    assert callable(is_ppv_placeholder_name)
    assert callable(is_ppv_channel)
    assert callable(get_ppv_event_title)

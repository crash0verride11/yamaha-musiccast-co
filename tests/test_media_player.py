"""Tests for the yamaha_musiccast media_player platform.

Covers the device class and icon logic in MusicCastMediaPlayer, which is
driven by the category_code the device reports in its getDeviceInfo response.
The coordinator parses this into a Category enum; the entity maps it to a
MediaPlayerDeviceClass and a matching MDI icon.
"""

from aiomusiccast_co.musiccast_data import Category
import pytest

from custom_components.yamaha_musiccast.media_player import (
    _CATEGORY_TO_DEVICE_CLASS,
    MusicCastMediaPlayer,
)
from homeassistant.components.media_player import MediaPlayerDeviceClass

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_player(coordinator) -> MusicCastMediaPlayer:
    """Return a main-zone media player backed by the given coordinator."""
    return MusicCastMediaPlayer("main", "My Speaker", "entry_id", coordinator)


# ---------------------------------------------------------------------------
# Category enum
# ---------------------------------------------------------------------------


class TestCategoryEnum:
    """Tests for the Category enum."""

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            (0, Category.UNKNOWN),
            (1, Category.AV_RECEIVER),
            (2, Category.SOUNDBAR),
            (3, Category.STEREO_RECEIVER),
            (4, Category.SUBWOOFER),
            (5, Category.MINI_SYSTEM),
            (6, Category.DESKTOP_AUDIO_1),
        ],
    )
    def test_known_codes(self, code, expected):
        """Test known category codes map to their Category members."""
        assert Category(code) == expected

    @pytest.mark.parametrize("code", [99, 255, -1, 1000])
    def test_unknown_codes_fall_back_to_unknown(self, code):
        """Test unrecognized category codes fall back to Category.UNKNOWN."""
        assert Category(code) == Category.UNKNOWN


# ---------------------------------------------------------------------------
# _CATEGORY_TO_DEVICE_CLASS mapping
# ---------------------------------------------------------------------------


class TestCategoryToDeviceClassMapping:
    """Tests for the category to device class mapping."""

    @pytest.mark.parametrize(
        ("category", "expected_class"),
        [
            (Category.AV_RECEIVER, MediaPlayerDeviceClass.RECEIVER),
            (Category.STEREO_RECEIVER, MediaPlayerDeviceClass.RECEIVER),
            (Category.SOUNDBAR, MediaPlayerDeviceClass.SPEAKER),
            (Category.SUBWOOFER, MediaPlayerDeviceClass.SPEAKER),
            (Category.MINI_SYSTEM, MediaPlayerDeviceClass.SPEAKER),
            (Category.DESKTOP_AUDIO_1, MediaPlayerDeviceClass.SPEAKER),
        ],
    )
    def test_known_categories(self, category, expected_class):
        """Test each known category maps to the expected device class."""
        assert _CATEGORY_TO_DEVICE_CLASS[category] == expected_class

    def test_unknown_not_in_mapping(self):
        """Test Category.UNKNOWN has no device class."""
        assert _CATEGORY_TO_DEVICE_CLASS.get(Category.UNKNOWN) is None

    def test_all_non_unknown_categories_covered(self):
        """Test every category except UNKNOWN has a device class."""
        for cat in Category:
            if cat != Category.UNKNOWN:
                assert cat in _CATEGORY_TO_DEVICE_CLASS, f"{cat} missing from mapping"


# ---------------------------------------------------------------------------
# MusicCastMediaPlayer.device_class and .icon
# ---------------------------------------------------------------------------


class TestMusicCastMediaPlayerDeviceClassAndIcon:
    """Tests for the media player's device class and icon."""

    @pytest.mark.parametrize(
        ("category", "expected_class"),
        [
            (Category.AV_RECEIVER, MediaPlayerDeviceClass.RECEIVER),
            (Category.STEREO_RECEIVER, MediaPlayerDeviceClass.RECEIVER),
            (Category.SOUNDBAR, MediaPlayerDeviceClass.SPEAKER),
            (Category.SUBWOOFER, MediaPlayerDeviceClass.SPEAKER),
            (Category.MINI_SYSTEM, MediaPlayerDeviceClass.SPEAKER),
            (Category.DESKTOP_AUDIO_1, MediaPlayerDeviceClass.SPEAKER),
            (Category.UNKNOWN, None),
        ],
    )
    def test_device_class(self, mock_coordinator, category, expected_class):
        """Test the device class follows the reported category."""
        mock_coordinator.data.category = category
        player = make_player(mock_coordinator)

        assert player.device_class == expected_class

    @pytest.mark.parametrize(
        ("category", "expected_icon"),
        [
            (Category.AV_RECEIVER, "mdi:audio-video"),
            (Category.STEREO_RECEIVER, "mdi:audio-video"),
            (Category.SOUNDBAR, "mdi:speaker"),
            (Category.SUBWOOFER, "mdi:speaker"),
            (Category.MINI_SYSTEM, "mdi:speaker"),
            (Category.DESKTOP_AUDIO_1, "mdi:speaker"),
            (Category.UNKNOWN, "mdi:speaker"),  # fallback
        ],
    )
    def test_icon(self, mock_coordinator, category, expected_icon):
        """Test the icon follows the device class, falling back to a speaker."""
        mock_coordinator.data.category = category
        player = make_player(mock_coordinator)

        assert player.icon == expected_icon

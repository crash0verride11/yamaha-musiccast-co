"""Tests for the yamaha_musiccast media_player platform.

Covers the device class and icon logic in MusicCastMediaPlayer, which is
driven by the category_code the device reports in its getDeviceInfo response.
The coordinator parses this into a Category enum; the entity maps it to a
MediaPlayerDeviceClass and a matching MDI icon.

Also covers async_browse_media turning library errors into BrowseError,
playing list entries by their full path, and searching list entries.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from aiomusiccast_co import (
    MusicCastConnectionException,
    MusicCastException,
    MusicCastMediaContent,
    MusicCastResponseException,
)
from aiomusiccast_co.musiccast_data import Category
import pytest

from custom_components.yamaha_musiccast.media_player import (
    _CATEGORY_TO_DEVICE_CLASS,
    MusicCastMediaPlayer,
)
from homeassistant.components.media_player import (
    BrowseError,
    MediaClass,
    MediaPlayerDeviceClass,
    MediaPlayerEntityFeature,
    SearchError,
    SearchMediaQuery,
)
from homeassistant.exceptions import HomeAssistantError

MEDIA_PLAYER = "custom_components.yamaha_musiccast.media_player"

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


# ---------------------------------------------------------------------------
# MusicCastMediaPlayer.async_browse_media error handling
# ---------------------------------------------------------------------------

BROWSE_ERRORS = [
    MusicCastResponseException("getListInfo response has no menu layer"),
    MusicCastException("list is still too deep after 20 return commands"),
    MusicCastConnectionException("timeout"),
    ValueError("unknown browse method"),
]


class TestBrowseMediaErrors:
    """Tests that library errors while browsing surface as BrowseError."""

    @pytest.fixture
    def player(self, mock_coordinator) -> MusicCastMediaPlayer:
        """Return a powered-on main-zone player."""
        mock_coordinator.data.zones["main"].power = "on"
        mock_coordinator.data.netusb_playback = "play"
        return make_player(mock_coordinator)

    @pytest.mark.parametrize("error", BROWSE_ERRORS)
    async def test_browse_media_error(self, player, error):
        """Test a failed browse raises BrowseError chained to the library error."""
        with (
            patch(
                "custom_components.yamaha_musiccast.media_player.MusicCastMediaContent.browse_media",
                AsyncMock(side_effect=error),
            ),
            pytest.raises(
                BrowseError, match="Could not browse media on My Speaker"
            ) as exc_info,
        ):
            await player.async_browse_media("music", "net_radio:0")

        assert exc_info.value.__cause__ is error

    @pytest.mark.parametrize("error", BROWSE_ERRORS)
    async def test_categories_error(self, player, error):
        """Test a failure listing the root categories raises BrowseError."""
        with (
            patch(
                "custom_components.yamaha_musiccast.media_player.MusicCastMediaContent.categories",
                MagicMock(side_effect=error),
            ),
            pytest.raises(BrowseError) as exc_info,
        ):
            await player.async_browse_media()

        assert exc_info.value.__cause__ is error


# ---------------------------------------------------------------------------
# Shared fixtures for the browse, play and search tests below
# ---------------------------------------------------------------------------

# A path-based entry content id, as aiomusiccast-co 0.18 builds them.
ENTRY_ID = "list:net_radio:2:3:1.3"
SEARCH_ENTRY_ID = "list:net_radio:1:2:2"


@pytest.fixture
def powered_player(mock_coordinator) -> MusicCastMediaPlayer:
    """Return a powered-on main-zone player on NET RADIO."""
    zone = mock_coordinator.data.zones["main"]
    zone.power = "on"
    zone.input = "net_radio"
    mock_coordinator.data.netusb_input = "net_radio"
    mock_coordinator.data.netusb_playback = "play"
    return make_player(mock_coordinator)


def search_results() -> MusicCastMediaContent:
    """Return a page of search results with a station and a Next Page folder."""
    return MusicCastMediaContent(
        can_browse=True,
        title="Search",
        children=[
            MusicCastMediaContent(
                can_play=True,
                title="Jazz FM",
                content_id="list:net_radio:3:0:2.s2:jazz",
                content_type="track",
                thumbnail="https://example.com/jazz.png",
            ),
            MusicCastMediaContent(
                can_browse=True,
                title="Next Page",
                content_id="list:net_radio:2:<>24:2.s2:jazz",
                content_type="directory",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# MusicCastMediaPlayer.async_play_media for list entries
# ---------------------------------------------------------------------------


class TestPlayListEntry:
    """Tests that list entries play through the library's path-based call."""

    async def test_plays_entry_by_path(self, powered_player, mock_coordinator):
        """Test a list entry is handed to play_list_entry with its full id."""
        with patch(
            f"{MEDIA_PLAYER}.MusicCastMediaContent.play_list_entry", AsyncMock()
        ) as play_list_entry:
            await powered_player.async_play_media("music", ENTRY_ID)

        play_list_entry.assert_awaited_once_with(
            mock_coordinator.musiccast, "main", ENTRY_ID
        )
        mock_coordinator.musiccast.play_list_media.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            ValueError("Not a playable list entry"),
            MusicCastException("list is still too deep after 20 return commands"),
        ],
    )
    async def test_play_error(self, powered_player, error):
        """Test a failed list entry play raises HomeAssistantError."""
        with (
            patch(
                f"{MEDIA_PLAYER}.MusicCastMediaContent.play_list_entry",
                AsyncMock(side_effect=error),
            ),
            pytest.raises(
                HomeAssistantError, match="Could not play .* on My Speaker"
            ) as exc_info,
        ):
            await powered_player.async_play_media("music", "list:net_radio:1:<>0:")

        assert exc_info.value.__cause__ is error


# ---------------------------------------------------------------------------
# MusicCastMediaPlayer.async_browse_media search flags
# ---------------------------------------------------------------------------


class TestBrowseMediaCanSearch:
    """Tests that browse results carry the library's can_search flags."""

    async def test_search_entry_child(self, powered_player):
        """Test a search entry in a list is marked searchable."""
        page = MusicCastMediaContent(
            can_browse=True,
            title="NET RADIO",
            content_id="list:net_radio:0:<>0:",
            content_type="directory",
            children=[
                MusicCastMediaContent(
                    can_browse=True,
                    can_search=True,
                    title="Search",
                    content_id=SEARCH_ENTRY_ID,
                    content_type="directory",
                ),
                MusicCastMediaContent(
                    can_browse=True,
                    title="Genres",
                    content_id="list:net_radio:1:0:0",
                    content_type="directory",
                ),
            ],
        )
        with patch(
            f"{MEDIA_PLAYER}.MusicCastMediaContent.browse_media",
            AsyncMock(return_value=page),
        ):
            result = await powered_player.async_browse_media("music", "input:net_radio")

        assert not result.can_search
        assert [child.can_search for child in result.children] == [True, False]

    async def test_opened_search_entry(self, powered_player):
        """Test an opened search entry is an empty searchable folder."""
        folder = MusicCastMediaContent(
            can_browse=True,
            can_search=True,
            title="Search",
            content_id=SEARCH_ENTRY_ID,
            content_type="directory",
        )
        with patch(
            f"{MEDIA_PLAYER}.MusicCastMediaContent.browse_media",
            AsyncMock(return_value=folder),
        ):
            result = await powered_player.async_browse_media("music", SEARCH_ENTRY_ID)

        assert result.can_search
        assert result.can_expand
        assert result.media_content_id == SEARCH_ENTRY_ID
        assert result.children == []


# ---------------------------------------------------------------------------
# MusicCastMediaPlayer.async_search_media
# ---------------------------------------------------------------------------


class TestSearchMedia:
    """Tests for searching through a list's search entry."""

    async def test_search_entry(self, powered_player, mock_coordinator):
        """Test searching a search entry returns its results as BrowseMedia."""
        with patch(
            f"{MEDIA_PLAYER}.MusicCastMediaContent.search",
            AsyncMock(return_value=search_results()),
        ) as search:
            result = await powered_player.async_search_media(
                SearchMediaQuery(search_query="jazz", media_content_id=SEARCH_ENTRY_ID)
            )

        search.assert_awaited_once_with(
            mock_coordinator.musiccast, "main", SEARCH_ENTRY_ID, "jazz", 24
        )
        station, next_page = result.result
        assert station.title == "Jazz FM"
        assert station.media_content_id == "list:net_radio:3:0:2.s2:jazz"
        assert station.media_content_type == MediaClass.TRACK
        assert station.media_class == MediaClass.TRACK
        assert station.can_play
        assert not station.can_expand
        assert station.thumbnail == "https://example.com/jazz.png"
        assert next_page.title == "Next Page"
        assert next_page.media_content_type == MediaClass.DIRECTORY
        assert next_page.can_expand
        assert not next_page.can_play

    @pytest.mark.parametrize("media_content_id", [None, ""])
    async def test_search_from_root(
        self, powered_player, mock_coordinator, media_content_id
    ):
        """Test a search without a list entry uses the current source."""
        with patch(
            f"{MEDIA_PLAYER}.MusicCastMediaContent.search",
            AsyncMock(return_value=search_results()),
        ) as search:
            result = await powered_player.async_search_media(
                SearchMediaQuery(search_query="jazz", media_content_id=media_content_id)
            )

        search.assert_awaited_once_with(
            mock_coordinator.musiccast, "main", "input:net_radio", "jazz", 24
        )
        assert len(result.result) == 2

    async def test_search_from_root_unsearchable_source(
        self, powered_player, mock_coordinator
    ):
        """Test a root search on a source without lists raises SearchError."""
        mock_coordinator.data.zones["main"].input = "bluetooth"
        with (
            patch(
                f"{MEDIA_PLAYER}.MusicCastMediaContent.search", AsyncMock()
            ) as search,
            pytest.raises(SearchError, match="can't be searched"),
        ):
            await powered_player.async_search_media(
                SearchMediaQuery(search_query="jazz")
            )

        search.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            ValueError("List entry is not capable of search"),
            ValueError("net_radio has no search-capable entry in its root menu"),
            MusicCastResponseException("getListInfo response has no menu layer"),
            MusicCastConnectionException("timeout"),
        ],
    )
    async def test_search_error(self, powered_player, error):
        """Test a failed search raises SearchError chained to the library error."""
        with (
            patch(
                f"{MEDIA_PLAYER}.MusicCastMediaContent.search",
                AsyncMock(side_effect=error),
            ),
            pytest.raises(
                SearchError, match="Could not search media on My Speaker"
            ) as exc_info,
        ):
            await powered_player.async_search_media(
                SearchMediaQuery(search_query="jazz", media_content_id=SEARCH_ENTRY_ID)
            )

        assert exc_info.value.__cause__ is error

    async def test_search_while_off(self, powered_player, mock_coordinator):
        """Test searching a turned off device raises SearchError."""
        mock_coordinator.data.zones["main"].power = "standby"
        with (
            patch(
                f"{MEDIA_PLAYER}.MusicCastMediaContent.search", AsyncMock()
            ) as search,
            pytest.raises(SearchError, match="has to be turned on"),
        ):
            await powered_player.async_search_media(
                SearchMediaQuery(search_query="jazz")
            )

        search.assert_not_called()


# ---------------------------------------------------------------------------
# MusicCastMediaPlayer.supported_features for browsing and searching
# ---------------------------------------------------------------------------


class TestBrowseAndSearchFeatures:
    """Tests that searching is offered together with browsing."""

    def test_on(self, powered_player):
        """Test a powered-on player supports browsing and searching."""
        features = powered_player.supported_features

        assert MediaPlayerEntityFeature.BROWSE_MEDIA in features
        assert MediaPlayerEntityFeature.SEARCH_MEDIA in features

    def test_off(self, powered_player, mock_coordinator):
        """Test a turned off player supports neither."""
        mock_coordinator.data.zones["main"].power = "standby"
        features = powered_player.supported_features

        assert MediaPlayerEntityFeature.BROWSE_MEDIA not in features
        assert MediaPlayerEntityFeature.SEARCH_MEDIA not in features

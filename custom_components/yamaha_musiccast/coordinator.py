"""The MusicCast integration."""

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from .aiomusiccast import MusicCastConnectionException
from .aiomusiccast.capabilities import Scene
from .aiomusiccast.musiccast_device import MusicCastData, MusicCastDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

if TYPE_CHECKING:
    from .entity import MusicCastDeviceEntity

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

type MusicCastConfigEntry = ConfigEntry["MusicCastDataUpdateCoordinator"]


class MusicCastDataUpdateCoordinator(DataUpdateCoordinator[MusicCastData]):
    """Class to manage fetching data from the API."""

    config_entry: MusicCastConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: MusicCastConfigEntry,
        client: MusicCastDevice,
    ) -> None:
        """Initialize."""
        self.musiccast = client
        self.selected_scenes: dict[str, Scene | None] = {}

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.entities: list[MusicCastDeviceEntity] = []

    async def _async_update_data(self) -> MusicCastData:
        """Update data via library."""
        try:
            await self.musiccast.fetch()
        except MusicCastConnectionException as exception:
            raise UpdateFailed(
                f"Error communicating with device: {exception}"
            ) from exception
        return self.musiccast.data

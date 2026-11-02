"""The MusicCast integration."""

import logging

import voluptuous as vol
from aiohttp import DummyCookieJar
from .aiomusiccast.musiccast_device import MusicCastDevice

from homeassistant.components import ssdp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .aiomusiccast.capabilities import Scene
from .const import CONF_SERIAL, CONF_UPNP_DESC, DOMAIN
from .coordinator import MusicCastConfigEntry, MusicCastDataUpdateCoordinator

SERVICE_SET_SCENE_INFO = "set_scene_info"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.BUTTON, Platform.MEDIA_PLAYER, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-level services."""

    async def handle_set_scene_info(call: ServiceCall) -> None:
        ha_device_id: str = call.data["device_id"]
        scene_num: int = int(call.data["scene_num"])
        name: str = call.data["name"]

        device = async_get_device_registry(hass).async_get(ha_device_id)
        if device is None:
            raise ServiceValidationError(f"Device {ha_device_id} not found.")

        config_entry_id = next(iter(device.config_entries), None)
        config_entry: MusicCastConfigEntry | None = (
            hass.config_entries.async_get_entry(config_entry_id) if config_entry_id else None
        )
        # runtime_data is unset until the entry finishes loading, so check state first
        if config_entry is None or config_entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                f"No active MusicCast coordinator for device {ha_device_id}."
            )
        coordinator = config_entry.runtime_data

        # Derive zone_id from the device identifier.
        # Main zone: identifier == coordinator.data.device_id
        # Other zones: identifier == "{device_id}_{zone_id}"
        yamaha_device_id = coordinator.data.device_id
        device_identifier = next(
            (ident for domain, ident in device.identifiers if domain == DOMAIN), None
        )
        if device_identifier == yamaha_device_id:
            zone_id = "main"
        elif device_identifier and device_identifier.startswith(f"{yamaha_device_id}_"):
            zone_id = device_identifier[len(yamaha_device_id) + 1:]
        else:
            raise ServiceValidationError(
                f"Could not resolve zone from device identifier '{device_identifier}'."
            )

        zone_data = coordinator.data.zones.get(zone_id)
        scene = next(
            (
                c for c in (zone_data.capabilities if zone_data else [])
                if isinstance(c, Scene) and c._num == scene_num
            ),
            None,
        )
        if scene is None:
            raise ServiceValidationError(
                f"Scene {scene_num} not found for zone '{zone_id}'."
            )

        await coordinator.musiccast.set_scene_info(zone_id, scene._num, name)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCENE_INFO,
        handle_set_scene_info,
        schema=vol.Schema({
            vol.Required("device_id"): str,
            vol.Required("scene_num"): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
            vol.Required("name"): str,
        }),
    )
    return True


async def get_upnp_desc(hass: HomeAssistant, host: str):
    """Get the upnp description URL for a given host, using the SSPD scanner."""
    ssdp_entries = await ssdp.async_get_discovery_info_by_st(hass, "upnp:rootdevice")
    matches = [w for w in ssdp_entries if w.ssdp_headers.get("_host", "") == host]
    upnp_desc = None
    for match in matches:
        if upnp_desc := match.ssdp_location:
            break

    if not upnp_desc:
        _LOGGER.warning(
            "The upnp_description was not found automatically, setting a default one"
        )
        upnp_desc = f"http://{host}:49154/MediaRenderer/desc.xml"
    return upnp_desc


async def async_setup_entry(hass: HomeAssistant, entry: MusicCastConfigEntry) -> bool:
    """Set up MusicCast from a config entry."""

    if entry.data.get(CONF_UPNP_DESC) is None:
        hass.config_entries.async_update_entry(
            entry,
            data={
                CONF_HOST: entry.data[CONF_HOST],
                CONF_SERIAL: entry.data["serial"],
                CONF_UPNP_DESC: await get_upnp_desc(hass, entry.data[CONF_HOST]),
            },
        )

    client = MusicCastDevice(
        entry.data[CONF_HOST],
        async_create_clientsession(hass, cookie_jar=DummyCookieJar()),
        entry.data[CONF_UPNP_DESC],
    )
    coordinator = MusicCastDataUpdateCoordinator(hass, entry, client=client)
    await coordinator.async_config_entry_first_refresh()
    coordinator.musiccast.build_capabilities()

    for zone_id, zone_data in coordinator.data.zones.items():
        first_scene = next(
            (c for c in zone_data.capabilities if isinstance(c, Scene)), None
        )
        if first_scene is not None:
            coordinator.selected_scenes[zone_id] = first_scene

    entry.runtime_data = coordinator

    await coordinator.musiccast.device.enable_polling()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MusicCastConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data.musiccast.device.disable_polling()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: MusicCastConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)

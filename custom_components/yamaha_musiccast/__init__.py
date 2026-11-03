"""The MusicCast integration."""

import logging

from aiohttp import DummyCookieJar
from aiomusiccast_co.capabilities import Scene
from aiomusiccast_co.musiccast_device import MusicCastDevice
import probatio

from homeassistant.components import ssdp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import BRAND, CONF_SERIAL, CONF_UPNP_DESC, DEFAULT_ZONE, DOMAIN
from .coordinator import MusicCastConfigEntry, MusicCastDataUpdateCoordinator

SERVICE_SET_SCENE_INFO = "set_scene_info"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-level services."""

    async def handle_set_scene_info(call: ServiceCall) -> None:
        ha_device_id: str = call.data["device_id"]
        scene_num: int = int(call.data["scene_num"])
        name: str = call.data["name"]

        device = dr.async_get(hass).async_get(ha_device_id)
        if device is None:
            raise ServiceValidationError(f"Device {ha_device_id} not found.")

        config_entry_id = next(iter(device.config_entries), None)
        config_entry: MusicCastConfigEntry | None = (
            hass.config_entries.async_get_entry(config_entry_id)
            if config_entry_id
            else None
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
            zone_id = device_identifier[len(yamaha_device_id) + 1 :]
        else:
            raise ServiceValidationError(
                f"Could not resolve zone from device identifier '{device_identifier}'."
            )

        # The zone's Scene capabilities are built from scene_information's keys.
        zone_data = coordinator.data.zones.get(zone_id)
        if zone_data is None or scene_num not in (zone_data.scene_information or {}):
            raise ServiceValidationError(
                f"Scene {scene_num} not found for zone '{zone_id}'."
            )

        await coordinator.musiccast.set_scene_info(zone_id, scene_num, name)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCENE_INFO,
        handle_set_scene_info,
        schema=probatio.Schema(
            {
                probatio.Required("device_id"): str,
                probatio.Required("scene_num"): probatio.All(
                    probatio.Coerce(int), probatio.Range(min=1, max=8)
                ),
                probatio.Required("name"): str,
            }
        ),
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


async def async_setup_entry(hass: HomeAssistant, entry: MusicCastConfigEntry) -> None:
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

    # Register the main device before forwarding platforms so the zone sub-devices
    # can resolve it as their via_device parent when they are added.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.data.device_id)},
        connections={
            (dr.CONNECTION_NETWORK_MAC, mac)
            for mac in coordinator.data.mac_addresses.values()
        },
        name=coordinator.data.zones[DEFAULT_ZONE].name,
        manufacturer=BRAND,
        model=coordinator.data.model_name,
        sw_version=str(coordinator.data.system_version),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))


async def async_unload_entry(hass: HomeAssistant, entry: MusicCastConfigEntry) -> None:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
    entry.runtime_data.musiccast.device.disable_polling()


async def async_reload_entry(hass: HomeAssistant, entry: MusicCastConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)

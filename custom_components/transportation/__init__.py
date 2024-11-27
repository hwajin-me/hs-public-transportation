from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
)

from custom_components.transportation.consts.defaults import DOMAIN, PLATFORMS
from custom_components.transportation.core.di import Container

_LOGGER = logging.getLogger(__name__)

container = Container()
container.wire(modules=[__name__])


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the price tracker component."""
    _LOGGER.debug("Setting up price tracker component {}".format(config))
    hass.data.setdefault(DOMAIN, {})

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Setting up entry and data {} > {}".format(entry, entry.data))
    _LOGGER.debug("Setting up entry and options {} > {}".format(entry, entry.options))

    # For upgrade options (1.0.0)
    data = entry.data
    options = entry.options

    hass.config_entries.async_update_entry(entry=entry, data=data, options=options)

    data = dict(data)
    listeners = entry.add_update_listener(options_update_listener)
    hass.data[DOMAIN][entry.entry_id] = data

    entry.async_on_unload(listeners)

    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    for e in entities:
        entity_registry.async_remove(e.entity_id)

    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    for d in devices:
        device_registry.async_update_device(d.id, remove_config_entry_id=entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    await hass.config_entries.async_reload(config_entry.entry_id)

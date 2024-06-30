"""Update platform for Teslemetry integration."""

from __future__ import annotations

from typing import Any

from tesla_fleet_api.const import Scope, TelemetryField

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TeslemetryUpdateStatus, TeslemetryTimestamp
from .entity import TeslemetryVehicleEntity
from .models import TeslemetryVehicleData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Teslemetry Update platform from a config entry."""


    async_add_entities(
        TeslemetryUpdateEntity(vehicle, Scope.VEHICLE_CMDS in entry.runtime_data.scopes)
        for vehicle in entry.runtime_data.vehicles
    )


class TeslemetryUpdateEntity(TeslemetryVehicleEntity, UpdateEntity):
    """Teslemetry Updates entity."""

    _attr_supported_features = UpdateEntityFeature.PROGRESS

    def __init__(
        self,
        data: TeslemetryVehicleData,
        scoped: bool,
    ) -> None:
        """Initialize the Update."""
        self.scoped = scoped
        super().__init__(
            data,
            "vehicle_state_software_update_status",
            timestamp_key=TeslemetryTimestamp.VEHICLE_STATE,
            streaming_key=TelemetryField.VERSION,
        )

    def _async_update_attrs(self) -> None:
        """Update the attributes of the entity."""

        # Supported Features
        if self.scoped and self._value in (
            TeslemetryUpdateStatus.AVAILABLE,
            TeslemetryUpdateStatus.SCHEDULED,
        ):
            self._attr_supported_features = (
                UpdateEntityFeature.PROGRESS | UpdateEntityFeature.INSTALL
            )
        else:
            self._attr_supported_features = UpdateEntityFeature.PROGRESS

        # Installed Version
        self._attr_installed_version = self.get("vehicle_state_car_version")
        if self._attr_installed_version is not None:
            # Remove build from version
            self._attr_installed_version = self._attr_installed_version.split(" ")[0]

        # Latest Version
        if self._value in (
            TeslemetryUpdateStatus.AVAILABLE,
            TeslemetryUpdateStatus.SCHEDULED,
            TeslemetryUpdateStatus.INSTALLING,
            TeslemetryUpdateStatus.DOWNLOADING,
            TeslemetryUpdateStatus.WIFI_WAIT,
        ):
            self._attr_latest_version = self.coordinator.data[
                "vehicle_state_software_update_version"
            ]
        else:
            self._attr_latest_version = self._attr_installed_version

        # In Progress
        if self._value in (
            TeslemetryUpdateStatus.SCHEDULED,
            TeslemetryUpdateStatus.INSTALLING,
        ):
            self._attr_in_progress = self.get(
                "vehicle_state_software_update_install_perc"
            )
        else:
            self._attr_in_progress = False

    def _async_value_from_stream(self, value) -> None:
        """Update the value of the entity."""
        if (value != " "):
            self._attr_installed_version = value

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        self.raise_for_scope()
        await self.wake_up_if_asleep()
        await self.handle_command(self.api.schedule_software_update(offset_sec=60))
        self._attr_state = TeslemetryUpdateStatus.INSTALLING
        self.async_write_ha_state()

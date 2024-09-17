"""Teslemetry Data Coordinator."""

from datetime import timedelta, datetime
from typing import Any

from tesla_fleet_api import EnergySpecific, VehicleSpecific
from tesla_fleet_api.const import VehicleDataEndpoint, TeslaEnergyPeriod
from tesla_fleet_api.exceptions import (
    TeslaFleetError,
    VehicleOffline,
    InvalidToken,
    SubscriptionRequired,
    Forbidden,
    LoginRequired,
    InternalServerError,
    ServiceUnavailable,
    GatewayTimeout,
    DeviceUnexpectedResponse
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from .const import LOGGER, TeslemetryState, DOMAIN, ENERGY_HISTORY_FIELDS
from .helpers import flatten

VEHICLE_INTERVAL = timedelta(seconds=30)
VEHICLE_WAIT = timedelta(minutes=15)
ENERGY_LIVE_INTERVAL = timedelta(seconds=30)
ENERGY_INFO_INTERVAL = timedelta(seconds=30)
ENERGY_HISTORY_INTERVAL = timedelta(seconds=30)


ENDPOINTS = [
    VehicleDataEndpoint.CHARGE_STATE,
    VehicleDataEndpoint.CLIMATE_STATE,
    VehicleDataEndpoint.DRIVE_STATE,
    VehicleDataEndpoint.LOCATION_DATA,
    VehicleDataEndpoint.VEHICLE_STATE,
    VehicleDataEndpoint.VEHICLE_CONFIG,
]




class TeslemetryVehicleDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the Teslemetry API."""

    updated_once = False
    pre2021: bool
    last_active: datetime
    failures: int = 0

    def __init__(
        self, hass: HomeAssistant, api: VehicleSpecific, product: dict
    ) -> None:
        """Initialize Teslemetry Vehicle Update Coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=f"Teslemetry Vehicle {api.vin}",
            update_interval=VEHICLE_INTERVAL,
        )
        self.api = api

        self.data = flatten(product)
        self.last_active = datetime.now()
        if (self.api.pre2021):
            LOGGER.info("Teslemetry will let {} sleep".format(api.vin))

    async def _async_update_data(self) -> dict[str, Any]:
        """Update vehicle data using Teslemetry API."""

        self.update_interval = VEHICLE_INTERVAL

        try:
            if self.data["state"] != TeslemetryState.ONLINE:
                response = await self.api.vehicle()
                self.data["state"] = response["response"]["state"]

            if self.data["state"] != TeslemetryState.ONLINE:
                return self.data

            response = await self.api.vehicle_data(endpoints=ENDPOINTS)
            data = response["response"]
        except VehicleOffline:
            self.data["state"] = TeslemetryState.OFFLINE
            return self.data
        except (InternalServerError, ServiceUnavailable, GatewayTimeout, DeviceUnexpectedResponse) as e:
            self.failures += 1
            if self.failures > 2:
                raise UpdateFailed("Multiple 5xx failures") from e
            return self.data
        except InvalidToken as e:
            raise ConfigEntryAuthFailed from e
        except (SubscriptionRequired,Forbidden,LoginRequired) as e:
            async_create_issue(
                self.hass,
                DOMAIN,
                self.api.vin,
                data=self.config_entry.entry_id,
                is_fixable=False,
                is_persistent=False,
                severity=IssueSeverity.ERROR,
                translation_key=e.key.lower()
                #translation_placeholders={"error": e.message}
            )
            raise UpdateFailed(e.message) from e
        except TeslaFleetError as e:
            raise UpdateFailed(e.message) from e
        except TypeError as e:
            raise UpdateFailed("Invalid response from Teslemetry") from e

        self.failures = 0
        self.hass.bus.fire("teslemetry_vehicle_data", data)

        if(self.api.pre2021):
            # Handle pre-2021 vehicles which cannot sleep by themselves
            if data["charge_state"].get("charging_state") == "Charging" or data["vehicle_state"].get("is_user_present") or data["vehicle_state"].get("sentry_mode"):
                # Vehicle is active, reset timer
                LOGGER.debug("Vehicle is active")
                self.last_active = datetime.now()
                self.update_interval = VEHICLE_INTERVAL
            else:
                elapsed = (datetime.now() - self.last_active)
                if elapsed > timedelta(minutes=20):
                    # Vehicle is awake for a reason, reset timer
                    LOGGER.debug("Ending sleep period")
                    self.last_active = datetime.now()
                elif elapsed > timedelta(minutes=15):
                    # Stop polling for 15 minutes
                    LOGGER.debug("Starting sleep period")
                    self.update_interval = VEHICLE_WAIT

        self.updated_once = True
        return flatten(data)


class TeslemetryEnergySiteLiveCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching energy site live status from the Teslemetry API."""

    failures: int = 0

    def __init__(self, hass: HomeAssistant, api: EnergySpecific) -> None:
        """Initialize Teslemetry Energy Site Live coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=f"Teslemetry Energy Site Live {api.energy_site_id}",
            update_interval=ENERGY_LIVE_INTERVAL,
        )
        self.api = api


    async def _async_update_data(self) -> dict[str, Any]:
        """Update energy site data using Teslemetry API."""

        try:
            data = (await self.api.live_status())["response"]
        except InvalidToken as e:
            raise ConfigEntryAuthFailed from e
        except (InternalServerError, ServiceUnavailable, GatewayTimeout, DeviceUnexpectedResponse) as e:
            self.failures += 1
            if self.failures > 2:
                raise UpdateFailed("Multiple 5xx failures") from e
            return self.data
        except TeslaFleetError as e:
            raise UpdateFailed(e.message) from e
        except TypeError as e:
            raise UpdateFailed("Invalid response from Teslemetry") from e

        # If the data isnt valid, placeholder it for safety
        if(not isinstance(data, dict)):
            data = {}

        self.hass.bus.fire("teslemetry_live_status", data)

        # Convert Wall Connectors from array to dict
        if isinstance(data.get("wall_connectors"),list):
            data["wall_connectors"] = {
                wc["din"]: wc for wc in data["wall_connectors"]
            }
        else:
            data["wall_connectors"] = {}

        return data


class TeslemetryEnergySiteInfoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching energy site info from the Teslemetry API."""

    failures: int = 0

    def __init__(self, hass: HomeAssistant, api: EnergySpecific, product: dict) -> None:
        """Initialize Teslemetry Energy Info coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=f"Teslemetry Energy Site Info {api.energy_site_id}",
            update_interval=ENERGY_INFO_INTERVAL,
        )
        self.api = api

        self.data = product

    async def _async_update_data(self) -> dict[str, Any]:
        """Update energy site data using Teslemetry API."""

        try:
            data = (await self.api.site_info())["response"]
        except InvalidToken as e:
            raise ConfigEntryAuthFailed from e
        except (InternalServerError, ServiceUnavailable, GatewayTimeout, DeviceUnexpectedResponse) as e:
            self.failures += 1
            if self.failures > 2:
                raise UpdateFailed("Multiple 5xx failures") from e
            return self.data
        except TeslaFleetError as e:
            raise UpdateFailed(e.message) from e
        except TypeError as e:
            raise UpdateFailed("Invalid response from Teslemetry") from e

        # If the data isnt valid, placeholder it for safety
        if(not isinstance(data, dict)):
            data = {}

        self.hass.bus.fire("teslemetry_site_info", data)

        return flatten(data)

class TeslemetryEnergyHistoryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching energy site info from the Teslemetry API."""

    failures: int = 0

    def __init__(self, hass: HomeAssistant, api: EnergySpecific) -> None:
        """Initialize Teslemetry Energy Info coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=f"Teslemetry Energy History ${api.energy_site_id}",
            update_interval=ENERGY_HISTORY_INTERVAL,
        )
        self.api = api
        self.data = {key: 0 for key in ENERGY_HISTORY_FIELDS}

    async def _async_update_data(self) -> dict[str, Any]:
        """Update energy site data using Teslemetry API."""

        try:
            data = (await self.api.energy_history(TeslaEnergyPeriod.DAY))["response"]
        except InvalidToken as e:
            raise ConfigEntryAuthFailed from e
        except (InternalServerError, ServiceUnavailable, GatewayTimeout, DeviceUnexpectedResponse) as e:
            self.failures += 1
            if self.failures > 2:
                raise UpdateFailed("Multiple 5xx failures") from e
            return self.data
        except TeslaFleetError as e:
            raise UpdateFailed(e.message) from e
        except TypeError as e:
            raise UpdateFailed("Invalid response from Teslemetry") from e

        # If the data isnt valid, placeholder it for safety
        if(not isinstance(data, dict)):
            data = {}

        # Add all time periods together
        output = {key: 0 for key in ENERGY_HISTORY_FIELDS}
        for period in data.get("time_series",[]):
            for key in ENERGY_HISTORY_FIELDS:
                output[key] += period.get(key,0)

        return output

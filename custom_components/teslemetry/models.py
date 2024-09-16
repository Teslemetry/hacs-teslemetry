"""The Teslemetry integration models."""

from __future__ import annotations
from homeassistant.util import dt as dt_util
from tesla_fleet_api import Teslemetry
import asyncio
from dataclasses import dataclass

from tesla_fleet_api import EnergySpecific, VehicleSpecific
from tesla_fleet_api.const import Scope

from teslemetry_stream import TeslemetryStream

from homeassistant.helpers.device_registry import DeviceInfo

from .coordinator import (
    TeslemetryEnergySiteInfoCoordinator,
    TeslemetryEnergySiteLiveCoordinator,
    TeslemetryEnergyHistoryCoordinator,
    TeslemetryVehicleDataCoordinator,
)


@dataclass
class TeslemetryData:
    """Data for the Teslemetry integration."""

    vehicles: list[TeslemetryVehicleData]
    energysites: list[TeslemetryEnergyData]
    scopes: list[Scope]
    teslemetry: Teslemetry


@dataclass
class TeslemetryVehicleData:
    """Data for a vehicle in the Teslemetry integration."""

    api: VehicleSpecific
    coordinator: TeslemetryVehicleDataCoordinator
    stream: TeslemetryStream
    vin: str
    device: DeviceInfo
    wakelock = asyncio.Lock()
    last_alert: str = dt_util.utcnow().isoformat()
    last_error: str = dt_util.utcnow().isoformat()
    remove_listeners: tuple[callable] = ()


@dataclass
class TeslemetryEnergyData:
    """Data for a vehicle in the Teslemetry integration."""

    api: EnergySpecific
    live_coordinator: TeslemetryEnergySiteLiveCoordinator
    info_coordinator: TeslemetryEnergySiteInfoCoordinator
    history_coordinator: TeslemetryEnergyHistoryCoordinator
    id: int
    device: DeviceInfo

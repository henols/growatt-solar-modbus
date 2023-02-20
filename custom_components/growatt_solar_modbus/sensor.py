"""GitHub sensor platform."""
from datetime import timedelta
import logging
from typing import Any, Optional

from growatt_client import GrowattClient
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo, DeviceEntryType
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
from homeassistant.util import Throttle

from .const import CONF_ADDRESS, CONF_NAME, CONF_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Time between updating data from Growatt inverter
SCAN_INTERVAL = timedelta(seconds=30)

calculated_sensors = []

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_PORT): cv.string,
        vol.Optional(CONF_ADDRESS, default=1): cv.positive_int,
        vol.Optional(CONF_NAME, default=""): cv.string,
    }
)


def create_sensor_entity_description(attr):
    """Creates a SensorEntityDescription from a client attribute"""
    return SensorEntityDescription(
        key=attr["name"],
        name=attr["description"],
        native_unit_of_measurement=unit_of_measurement(attr),
        device_class=sensor_device_class(attr),
        state_class=sensor_state_class(attr),
    )


def sensor_state_class(attr):
    """Get sensort state class"""
    if attr["name"].endswith("lifetime") or attr["name"].endswith("today"):
        return SensorStateClass.TOTAL_INCREASING
    return None


def sensor_device_class(attr):
    """Get sensor device class"""
    unit = attr["unit"]
    if unit == "kWh":
        return SensorDeviceClass.ENERGY
    if unit == "kW":
        return SensorDeviceClass.POWER
    if unit == "V":
        return SensorDeviceClass.VOLTAGE
    if unit == "A":
        return SensorDeviceClass.CURRENT
    if unit == "%":
        return SensorDeviceClass.BATTERY
    return None


def unit_of_measurement(attr):
    """Get tue unit type"""
    return attr["unit"]


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the sensor platform."""
    port = config[CONF_PORT]
    address = config[CONF_ADDRESS]
    name = config[CONF_NAME]

    client = GrowattClient(port, address)

    await client.update_hardware_info()
    serial_number = client.get_serial_number()

    _LOGGER.debug("Serial number: %s", serial_number)

    probe = GrowattClientDataProbe(client)

    if name == "":
        name = serial_number

    sensors = [
        GrowattClientSensor(
            name, serial_number, create_sensor_entity_description(attr), probe
        )
        for attr in client.get_attributes()
    ]

    async_add_entities(sensors, update_before_add=True)


class GrowattClientDataProbe:
    """The class for handling data retrieval."""

    def __init__(self, client: GrowattClient) -> None:
        """Initialize the probe."""
        self.client = client
        self.data = []

    @Throttle(SCAN_INTERVAL)
    async def update(self):
        """Update probe data."""
        self.data = await self.client.async_update()
        _LOGGER.debug("Updated: %s", self.data)

    def get_data(self, name) -> Any:
        """Get the data."""
        if name not in self.data:
            return None
        return self.data[str(name)]

    def has_data(self):
        """Checks if probe has any data"""
        return bool(self.data)

    def __format__(self, key: str) -> str:
        value = self.get_data(key)
        if value is None:
            return ""
        return str(value)


class GrowattClientSensor(SensorEntity):
    """Representation of a GitHub Repo sensor."""

    def __init__(
        self,
        name: str,
        serial,
        description: SensorEntityDescription,
        probe: GrowattClientDataProbe,
        template=None,
    ):
        super().__init__()
        self.probe = probe
        self.entity_description = description
        self._attr_unique_id = serial + "_" + description.key
        self._attr_name = f"{name} {description.name}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, serial)},
            manufacturer="Growatt",
            name=name,
        )
        self.template = template

    @property
    def available(self):
        return self.probe.has_data()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.probe.get_data(self.entity_description.key)

    async def async_update(self) -> None:
        """Get the latest data from the Growat API and updates the state."""
        await self.probe.update()

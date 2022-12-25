"""Support for SimpliSafe binary sensors."""
from __future__ import annotations

from simplipy.device import DeviceTypes
from simplipy.device.camera import Camera, CameraTypes
from simplipy.device.sensor.v3 import SensorV3
from simplipy.system.v3 import SystemV3
from simplipy.websocket import EVENT_DOORBELL_DETECTED, EVENT_CAMERA_MOTION_DETECTED

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimpliSafe, SimpliSafeEntity
from .const import DOMAIN, LOGGER

SUPPORTED_BATTERY_SENSOR_TYPES = [
    DeviceTypes.CARBON_MONOXIDE,
    DeviceTypes.ENTRY,
    DeviceTypes.GLASS_BREAK,
    DeviceTypes.KEYPAD,
    DeviceTypes.LEAK,
    DeviceTypes.LOCK_KEYPAD,
    DeviceTypes.MOTION,
    DeviceTypes.SIREN,
    DeviceTypes.SMOKE,
    DeviceTypes.TEMPERATURE,
]

TRIGGERED_SENSOR_TYPES = {
    DeviceTypes.CARBON_MONOXIDE: BinarySensorDeviceClass.GAS,
    DeviceTypes.ENTRY: BinarySensorDeviceClass.DOOR,
    DeviceTypes.GLASS_BREAK: BinarySensorDeviceClass.SAFETY,
    DeviceTypes.LEAK: BinarySensorDeviceClass.MOISTURE,
    DeviceTypes.MOTION: BinarySensorDeviceClass.MOTION,
    DeviceTypes.SIREN: BinarySensorDeviceClass.SAFETY,
    DeviceTypes.SMOKE: BinarySensorDeviceClass.SMOKE,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SimpliSafe binary sensors based on a config entry."""
    simplisafe = hass.data[DOMAIN][entry.entry_id]

    sensors: list[BatteryBinarySensor | TriggeredBinarySensor] = []

    for system in simplisafe.systems.values():
        if system.version == 2:
            LOGGER.info("Skipping sensor setup for V2 system: %s", system.system_id)
            continue

        for sensor in system.sensors.values():
            if sensor.type in TRIGGERED_SENSOR_TYPES:
                sensors.append(
                    TriggeredBinarySensor(
                        simplisafe,
                        system,
                        sensor,
                        TRIGGERED_SENSOR_TYPES[sensor.type],
                    )
                )
            if sensor.type in SUPPORTED_BATTERY_SENSOR_TYPES:
                sensors.append(BatteryBinarySensor(simplisafe, system, sensor))

        for cam in system.cameras.values():
            sensors.append(CameraMotionBinarySensor(simplisafe, system, cam))
            if cam.camera_type == CameraTypes.DOORBELL:
                sensors.append(CameraDoorbellBinarySensor(simplisafe, system, cam))

    async_add_entities(sensors)


class TriggeredBinarySensor(SimpliSafeEntity, BinarySensorEntity):
    """Define a binary sensor related to whether an entity has been triggered."""

    def __init__(
        self,
        simplisafe: SimpliSafe,
        system: SystemV3,
        sensor: SensorV3,
        device_class: BinarySensorDeviceClass,
    ) -> None:
        """Initialize."""
        super().__init__(simplisafe, system, device=sensor)

        self._attr_device_class = device_class
        self._device: SensorV3

    @callback
    def async_update_from_rest_api(self) -> None:
        """Update the entity with the provided REST API data."""
        self._attr_is_on = self._device.triggered


class BatteryBinarySensor(SimpliSafeEntity, BinarySensorEntity):
    """Define a SimpliSafe battery binary sensor entity."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, simplisafe: SimpliSafe, system: SystemV3, sensor: SensorV3
    ) -> None:
        """Initialize."""
        super().__init__(simplisafe, system, device=sensor)

        self._attr_name = "Battery"
        self._attr_unique_id = f"{super().unique_id}-battery"
        self._device: SensorV3

    @callback
    def async_update_from_rest_api(self) -> None:
        """Update the entity with the provided REST API data."""
        self._attr_is_on = self._device.low_battery

class CameraDoorbellBinarySensor(SimpliSafeEntity, BinarySensorEntity):
    """Define a SimpliSafe camera binary sensor entity."""
    
    _attr_device_class: BinarySensorDeviceClass.OCCUPANCY
    _attr_is_on = False

    def __init__(
        self,
        simplisafe: SimpliSafe,
        system: SystemV3,
        camera: Camera,
        ) -> None:
        """Initialize."""
        super().__init__(
            simplisafe,
            system,
            device=camera,
            additional_websocket_events=[EVENT_DOORBELL_DETECTED]
        )

        self._device: Camera

        self._attr_name = "Doorbell"
        self._attr_unique_id = f"{super().unique_id}-doorbell"

    @callback
    def async_update_from_rest_api(self):
        """No updates as camera sensor status cannot be read via API."""
        return

    @callback
    def async_update_from_websocket_event(self, event):
        """Update the entity with the provided websocket event data."""
        LOGGER.critical(event)
        self._attr_is_on = True

        @callback
        def clear_delay_listener(now):
            """Clear motion sensor after delay."""
            self._attr_is_on = False
            self.async_write_ha_state()

        async_call_later(
            self.hass, MOTION_SENSOR_TRIGGER_CLEAR, clear_delay_listener
        )

class CameraMotionBinarySensor(SimpliSafeEntity, BinarySensorEntity):
    """Define a SimpliSafe camera binary sensor entity."""

    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_is_on = False

    def __init__(
        self,
        simplisafe: SimpliSafe,
        system: SystemV3,
        camera: Camera,
        ) -> None:
        """Initialize."""
        super().__init__(
            simplisafe,
            system,
            device=camera,
            additional_websocket_events=[EVENT_CAMERA_MOTION_DETECTED]
        )

        self._device: Camera

        self._attr_name = "Motion"
        self._attr_unique_id = f"{super().unique_id}-motion"

    @callback
    def async_update_from_rest_api(self):
        """No updates as camera sensor status cannot be read via API."""
        return

    @callback
    def async_update_from_websocket_event(self, event):
        """Update the entity with the provided websocket event data."""
        LOGGER.critical(event)
        self._attr_is_on = True

        @callback
        def clear_delay_listener(now):
            """Clear motion sensor after delay."""
            self._attr_is_on = False
            self.async_write_ha_state()

        async_call_later(
            self.hass, MOTION_SENSOR_TRIGGER_CLEAR, clear_delay_listener
        )

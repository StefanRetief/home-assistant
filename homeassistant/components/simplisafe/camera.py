"""This component provides support for SimpliSafe cameras."""
import asyncio

from haffmpeg.camera import CameraMjpeg
from haffmpeg.tools import IMAGE_JPEG, ImageFrame

from simplipy.device.camera import Camera as SimpliCam, DEFAULT_VIDEO_WIDTH
from simplipy.system import SystemStates
from simplipy.system.v3 import SystemV3

from homeassistant.components.camera import Camera
from homeassistant.components.ffmpeg import DATA_FFMPEG, FFmpegManager
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_stream

from . import SimpliSafe, SimpliSafeEntity
from .const import DOMAIN, LOGGER


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up SimpliCam cameras based on a config entry."""
    simplisafe: SimpliSafe = hass.data[DOMAIN][entry.entry_id]

    cameras: list[SimpliSafeCamera] = []

    for system in simplisafe.systems.values():
        if system.version == 2:
            LOGGER.info("Skipping sensor setup for V2 system: %s", system.system_id)
            continue

        for cam in system.cameras.values():
            cameras.append(SimpliSafeCamera(simplisafe, system, hass.data[DATA_FFMPEG], cam))


    async_add_entities(cameras)


class SimpliSafeCamera(SimpliSafeEntity, Camera):
    """An implementation of a SimpliCam camera."""

    def __init__(self, simplisafe: SimpliSafe, system: SystemV3, ffmpeg: FFmpegManager, camera: SimpliCam):
        """Initialize a SimpliCam camera."""
        Camera.__init__(self)
        super().__init__(
            simplisafe,
            system,
            device=camera,
        )

        self._device: SimpliCam
        self._ffmpeg = ffmpeg
        self._last_image = None

        self._attr_name = "Camera"
        self._attr_unique_id = f"{super().unique_id}-camera"

        self._is_online = self._device.status == "online"
        self._is_subscribed = self._device.subscription_enabled
        

    @property
    def is_on(self):
        """Return true if on."""
        return self._is_online and self._is_subscribed

    @callback
    def async_update_from_rest_api(self):
        """Update the entity with the provided REST API data."""
        self._is_online = self._device.status == "online"
        self._is_subscribed = self._device.subscription_enabled

    @property
    def _video_url(self):
        """Provide the image URL."""
        url = self._device.video_url()
        return '-re {} -i "{}"'.format(
            self.auth_headers, url
        )

    @property
    def auth_headers(self):
        """Generate auth headers."""
        return '-headers "Authorization: Bearer {}"'.format(
            self._simplisafe._api.access_token
        )

    @property
    def is_shutter_open(self):
        """Check if the camera shutter is open."""
        if self._system.state == SystemStates.off:
            return self._device.shutter_open_when_off
        if self._system.state == SystemStates.home:
            return self._device.shutter_open_when_home
        if self._system.state == SystemStates.away:
            return self._device.shutter_open_when_away
        return True

    async def stream_source(self) -> str | None:
        return self._video_url

    async def async_device_image(self):
        """Return a still image response from the camera."""
        if not self.is_shutter_open:
            """Shutter is currently closed, return last image."""
            return self._last_image

        ffmpeg = ImageFrame(self._ffmpeg.binary)

        if self._video_url is None:
            return

        image = await asyncio.shield(
            ffmpeg.get_image(
                self._video_url,
                output_format=IMAGE_JPEG,
            )
        )
        self._last_image = image
        return image

    async def handle_async_mjpeg_stream(self, request):
        """Generate an HTTP MJPEG stream from the camera."""
        if self._video_url is None:
            return

        LOGGER.warn(self._video_url)

        stream = CameraMjpeg(self._ffmpeg.binary)
        await stream.open_camera(
            self._video_url,
        )

        try:
            stream_reader = await stream.get_reader()
            return await async_aiohttp_proxy_stream(
                self.hass,
                request,
                stream_reader,
                self._ffmpeg.ffmpeg_stream_content_type,
            )
        finally:
            await stream.close()
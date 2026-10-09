"""SVG tooth diagram of relative coverage, adapted from PPP01's image branch.

Grey means missed, red means very little coverage, orange means below target,
and green means at least 75% of the session's average contribution per zone.
Uses the same unit-independent ratings as the per-session zone history.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_NAME,
    CONF_MAC_ADDRESS,
    DATA_LAST_BRUSH_AREAS,
    DATA_LAST_BRUSH_TIME,
    DOMAIN,
    TOOTH_AREA_NAMES,
)
from .coordinator import OcleanCoordinator
from .entity import OcleanEntity
from .zone_utils import zone_ratings

# SVG canvas.
_W, _H = 300, 460
_MID_Y = 230  # horizontal divider between upper and lower jaw

# Arch geometry — ellipse parameters for tooth centre positions.
_UPPER = {"cx": _W / 2, "cy": _MID_Y - 8, "rx": 80, "ry": 160, "start": 185, "end": 355}
_LOWER = {"cx": _W / 2, "cy": _MID_Y + 8, "rx": 80, "ry": 160, "start": 5, "end": 175}
_TEETH_PER_JAW = 16
_TOOTH_R = 15

_BG = "#E0E0E0"
_BG_STROKE = "#D0D0D0"


_RATING_COLORS = {"good": "#4CAF50", "ok": "#FF9800", "poor": "#F44336", "missed": None}


def _zone_colors(areas: dict[str, int]) -> dict[str, str | None]:
    """Use the same relative zone ratings as session history, not raw pressure.

    Elite Pro sends time-distribution values. Other firmware may use slots;
    rating shares of the total keeps the diagram independent of those units.
    """
    ratings = zone_ratings([areas.get(zone, 0) for zone in TOOTH_AREA_NAMES])
    return {zone: _RATING_COLORS[rating] for zone, rating in zip(TOOTH_AREA_NAMES, ratings or [], strict=True)}


# ------------------------------------------------------------------
# SVG helpers
# ------------------------------------------------------------------


def _tooth_positions(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    start_deg: float,
    end_deg: float,
    count: int,
) -> list[tuple[float, float]]:
    """Return (x, y) centres for *count* teeth along an elliptical arc."""
    start_rad = math.radians(start_deg)
    end_rad = math.radians(end_deg)
    return [
        (
            cx + rx * math.cos(start_rad + (end_rad - start_rad) * i / (count - 1)),
            cy + ry * math.sin(start_rad + (end_rad - start_rad) * i / (count - 1)),
        )
        for i in range(count)
    ]


# ------------------------------------------------------------------
# SVG generation
# ------------------------------------------------------------------


def _tooth_zone_map(
    n_teeth: int,
    jaw_name: str,
    zone_count: int,
) -> list[str]:
    """Return a list mapping each tooth index to its section name (left/center/right).

    Upper jaw arc: first half = left, second half = right (or left/center/right for 12).
    Lower jaw arc: reversed (first half = right, second half = left).
    """
    if zone_count >= 12:
        third = n_teeth // 3
        sections = ["left"] * third + ["center"] * (n_teeth - 2 * third) + ["right"] * third
    else:
        mid = n_teeth // 2
        sections = ["left"] * mid + ["right"] * (n_teeth - mid)
    if jaw_name == "lower":
        sections = list(reversed(sections))
    return sections


def _semicircle_path(
    tx: float,
    ty: float,
    r: float,
    cx: float,
    cy: float,
    *,
    outer: bool,
) -> str:
    """SVG path for a semicircle split along the radial direction."""
    angle = math.atan2(ty - cy, tx - cx)
    perp = angle + math.pi / 2
    p1x = tx + r * math.cos(perp)
    p1y = ty + r * math.sin(perp)
    p2x = tx - r * math.cos(perp)
    p2y = ty - r * math.sin(perp)
    sweep = 1 if outer else 0
    return f"M {p1x:.1f} {p1y:.1f} A {r} {r} 0 0 {sweep} {p2x:.1f} {p2y:.1f} Z"


def _generate_svg(areas: dict[str, int]) -> str:
    """Generate a complete SVG string for the given per-zone brushing contributions.

    Uses per-tooth semicircles for the inner/outer split — no nested
    clip-paths needed.  Each tooth is assigned to its section (left,
    center, right) based on its position in the arc.

    Colours describe relative coverage, not pressure or a medical assessment.
    """
    elems: list[str] = []
    colors = _zone_colors(areas)

    for jaw_name, jaw in [("upper", _UPPER), ("lower", _LOWER)]:
        cx, cy = jaw["cx"], jaw["cy"]
        rx, ry = jaw["rx"], jaw["ry"]
        start, end = jaw["start"], jaw["end"]

        positions = _tooth_positions(cx, cy, rx, ry, start, end, _TEETH_PER_JAW)
        zone_map = _tooth_zone_map(_TEETH_PER_JAW, jaw_name, 8)

        for idx, (tx, ty) in enumerate(positions):
            section = zone_map[idx]
            zone_out = f"{jaw_name}_{section}_out"
            zone_in = f"{jaw_name}_{section}_in"
            color_out = colors.get(zone_out)
            color_in = colors.get(zone_in)

            # Grey background tooth.
            elems.append(
                f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{_TOOTH_R}" '
                f'fill="{_BG}" stroke="{_BG_STROKE}" stroke-width="0.3"/>'
            )

            # Outer half (semicircle facing away from arch centre).
            if color_out:
                d = _semicircle_path(tx, ty, _TOOTH_R, cx, cy, outer=True)
                elems.append(f'<path d="{d}" fill="{color_out}" opacity="0.9"/>')

            # Inner half (semicircle facing toward arch centre).
            if color_in:
                d = _semicircle_path(tx, ty, _TOOTH_R, cx, cy, outer=False)
                elems.append(f'<path d="{d}" fill="{color_in}" opacity="0.9"/>')

    # Divider line and labels.
    elems.append(
        f'<line x1="20" y1="{_MID_Y}" x2="{_W - 20}" y2="{_MID_Y}" '
        f'stroke="{_BG_STROKE}" stroke-width="1" stroke-dasharray="4,4"/>'
    )
    elems.append(
        f'<text x="12" y="{_MID_Y + 5}" font-family="Arial,sans-serif" '
        f'font-size="13" fill="#BBB" text-anchor="middle">L</text>'
    )
    elems.append(
        f'<text x="{_W - 12}" y="{_MID_Y + 5}" font-family="Arial,sans-serif" '
        f'font-size="13" fill="#BBB" text-anchor="middle">R</text>'
    )

    elems_str = "\n  ".join(elems)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {_W} {_H}" width="{_W}" height="{_H}">\n'
        f'  <rect width="{_W}" height="{_H}" fill="white" rx="8"/>\n'
        f"  {elems_str}\n"
        f"</svg>\n"
    )


# ------------------------------------------------------------------
# Home Assistant entity
# ------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Oclean brush coverage image entity."""
    coordinator: OcleanCoordinator = hass.data[DOMAIN][entry.entry_id]
    mac = entry.data[CONF_MAC_ADDRESS]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Oclean")
    async_add_entities([OcleanBrushCoverageImage(coordinator, mac, device_name)])


class OcleanBrushCoverageImage(OcleanEntity, ImageEntity):
    """Image entity showing a colour-coded brush coverage diagram."""

    _attr_content_type = "image/svg+xml"
    _attr_translation_key = "brush_coverage"

    def __init__(
        self,
        coordinator: OcleanCoordinator,
        mac: str,
        device_name: str,
    ) -> None:
        OcleanEntity.__init__(self, coordinator, mac, device_name, "brush_coverage")
        ImageEntity.__init__(self, coordinator.hass)
        self._svg_bytes: bytes | None = None
        self._render_key: tuple | None = None
        self._sync_image_cache()

    def _get_areas(self) -> dict[str, int] | None:
        if self.coordinator.data is None:
            return None
        areas = self.coordinator.data.get(DATA_LAST_BRUSH_AREAS)
        return areas if isinstance(areas, dict) else None

    def _sync_image_cache(self) -> None:
        """Refresh after every new session, even when its zone values are identical."""
        areas = self._get_areas()
        ts = self.coordinator.data.get(DATA_LAST_BRUSH_TIME) if self.coordinator.data is not None else None
        key = (ts, tuple(sorted(areas.items()))) if areas is not None else None
        if key != self._render_key:
            self._render_key = key
            self._svg_bytes = None
            self._attr_image_last_updated = datetime.now(UTC) if areas is not None else None

    def _handle_coordinator_update(self) -> None:
        """Invalidate the SVG cache and update the dashboard image timestamp."""
        self._sync_image_cache()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return the brush coverage SVG as bytes."""
        self._sync_image_cache()
        areas = self._get_areas()
        if areas is None:
            return None
        if self._svg_bytes is None:
            self._svg_bytes = _generate_svg(areas).encode("utf-8")
        return self._svg_bytes

"""Verify the PPP01 dental diagram and Elite Pro's relative zone colours."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from custom_components.oclean_ble.const import DATA_LAST_BRUSH_AREAS, DATA_LAST_BRUSH_TIME, TOOTH_AREA_NAMES
from custom_components.oclean_ble.image import OcleanBrushCoverageImage, _generate_svg, _zone_colors, async_setup_entry


def _entity(areas=None, ts=1700000000):
    coordinator = MagicMock()
    coordinator.data = {DATA_LAST_BRUSH_AREAS: areas, DATA_LAST_BRUSH_TIME: ts}
    coordinator.hass.data = {}
    return OcleanBrushCoverageImage(coordinator, "AA:BB:CC:DD:EE:FF", "Oclean")


class TestCoverageSvg:
    def test_valid_svg_has_32_teeth_and_two_jaws(self):
        svg = _generate_svg(dict.fromkeys(TOOTH_AREA_NAMES, 15))
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert len(root.findall("{http://www.w3.org/2000/svg}circle")) == 32
        assert len(root.findall("{http://www.w3.org/2000/svg}path")) == 64
        assert len(svg) < 15000

    def test_empty_zones_remain_grey(self):
        svg = _generate_svg({})
        assert "#4CAF50" not in svg
        assert "#FF9800" not in svg
        assert "#F44336" not in svg

    def test_elite_pro_time_distribution_is_not_mistaken_for_pressure(self):
        colors = _zone_colors(dict.fromkeys(TOOTH_AREA_NAMES, 200))
        assert set(colors.values()) == {"#4CAF50"}

    def test_rating_matches_history_and_is_unit_independent(self):
        areas = dict(zip(TOOTH_AREA_NAMES, [0, 1, 5, 15, 15, 15, 15, 14], strict=True))
        colors = _zone_colors(areas)
        assert colors[TOOTH_AREA_NAMES[0]] is None
        assert colors[TOOTH_AREA_NAMES[1]] == "#F44336"
        assert colors[TOOTH_AREA_NAMES[2]] == "#FF9800"
        assert colors[TOOTH_AREA_NAMES[3]] == "#4CAF50"
        assert _zone_colors({k: v * 10 for k, v in areas.items()}) == colors

    def test_labels_and_colour_overlays_exist(self):
        svg = _generate_svg(dict(zip(TOOTH_AREA_NAMES, [0, 1, 5, 15, 15, 15, 15, 14], strict=True)))
        for fragment in [">L</text>", ">R</text>", "#4CAF50", "#FF9800", "#F44336"]:
            assert fragment in svg


class TestCoverageImageEntity:
    def test_initial_image_has_timestamp_and_correct_identity(self):
        entity = _entity(dict.fromkeys(TOOTH_AREA_NAMES, 10))
        assert entity._attr_unique_id == "AA:BB:CC:DD:EE:FF_brush_coverage"
        assert entity._attr_translation_key == "brush_coverage"
        assert entity._attr_content_type == "image/svg+xml"
        assert entity._attr_image_last_updated is not None
        assert entity._attr_image_last_updated.tzinfo is not None

    async def test_missing_areas_returns_none(self):
        assert await _entity().async_image() is None

    async def test_no_coordinator_data_returns_none(self):
        entity = _entity()
        entity.coordinator.data = None
        assert entity.available is False
        assert await entity.async_image() is None

    async def test_image_bytes_are_cached(self):
        entity = _entity(dict.fromkeys(TOOTH_AREA_NAMES, 10))
        first = await entity.async_image()
        assert first.startswith(b"<svg")
        assert await entity.async_image() is first

    async def test_new_session_refreshes_even_when_zone_values_match(self):
        entity = _entity(dict.fromkeys(TOOTH_AREA_NAMES, 10))
        first = await entity.async_image()
        before = entity._attr_image_last_updated
        entity.coordinator.data[DATA_LAST_BRUSH_TIME] += 3600
        entity._handle_coordinator_update()
        assert entity._attr_image_last_updated > before
        assert await entity.async_image() == first
        assert await entity.async_image() is not first

    async def test_mutating_zone_dict_refreshes_cached_image(self):
        areas = dict.fromkeys(TOOTH_AREA_NAMES, 10)
        entity = _entity(areas)
        first = await entity.async_image()
        areas[TOOTH_AREA_NAMES[0]] = 0
        assert await entity.async_image() != first

    async def test_missing_data_clears_old_image(self):
        entity = _entity(dict.fromkeys(TOOTH_AREA_NAMES, 10))
        await entity.async_image()
        entity.coordinator.data.pop(DATA_LAST_BRUSH_AREAS)
        entity._handle_coordinator_update()
        assert await entity.async_image() is None
        assert entity._attr_image_last_updated is None

    async def test_setup_registers_image(self):
        entity = _entity(dict.fromkeys(TOOTH_AREA_NAMES, 10))
        hass = entity.coordinator.hass
        hass.data = {"oclean_ble": {"test": entity.coordinator}}
        entry = MagicMock(entry_id="test")
        entry.data = {"mac_address": "AA:BB:CC:DD:EE:FF"}
        add = MagicMock()
        await async_setup_entry(hass, entry, add)
        assert isinstance(add.call_args.args[0][0], OcleanBrushCoverageImage)

"""Cross-device custom programmes, persistence and service/selection wiring."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.oclean_ble import async_setup_entry
from custom_components.oclean_ble.const import DOMAIN, SIGNAL_PROGRAMS_UPDATED
from custom_components.oclean_ble.programs import CustomProgramStore
from tests.test_coordinator import _make_bleak_client, _make_coordinator
from tests.test_init import _make_entry, _make_hass
from tests.test_select import _make_entity


def _store():
    hass = MagicMock()
    store = CustomProgramStore(hass)
    store._store.async_save = AsyncMock()
    store._store.async_load = AsyncMock(return_value=None)
    return store


class TestCustomProgramStore:
    async def test_save_reload_and_delete(self):
        store = _store()
        with patch("custom_components.oclean_ble.programs.async_dispatcher_send") as signal:
            pnum = await store.async_save(" Evening ", [(2, 90), (2, 90)])
            assert pnum == 120
            saved = store._store.async_save.call_args.args[0]
            assert saved["programs"]["120"]["name"] == "Evening"
            assert saved["programs"]["120"]["steps"] == [[2, 90], [2, 90]]
            signal.assert_called_with(store._hass, SIGNAL_PROGRAMS_UPDATED)
            loaded = _store()
            loaded._store.async_load.return_value = saved
            await loaded.async_load()
            assert loaded.get(120) == {"name": "Evening", "steps": [(2, 90), (2, 90)]}
            await loaded.async_delete(120)
            assert loaded.get(120) is None
            assert loaded.list() == {}

    async def test_concurrent_saves_allocate_distinct_numbers(self):
        store = _store()
        first, second = await asyncio.gather(
            store.async_save("First", [(2, 60)]), store.async_save("Second", [(3, 90)])
        )
        assert (first, second) == (120, 121)
        assert len(store._store.async_save.call_args.args[0]["programs"]) == 2

    async def test_load_is_idempotent(self):
        store = _store()
        await store.async_load()
        await store.async_save("New", [(2, 60)])
        await store.async_load()
        store._store.async_load.assert_awaited_once()
        assert store.get(120)["name"] == "New"

    async def test_load_ignores_invalid_saved_programmes(self):
        store = _store()
        store._store.async_load.return_value = {
            "programs": {
                "120": {"name": "OK", "steps": [[2, 60]]},
                "256": {"name": "Bad number", "steps": [[2, 60]]},
                "121": {"name": "Bad gear", "steps": [[99, 60]]},
                "122": {"name": "", "steps": [[2, 60]]},
                "123": {"missing": "fields"},
            }
        }
        await store.async_load()
        assert set(store.list()) == {120}

    @pytest.mark.parametrize("pnum", [-1, 119, 256])
    async def test_pnum_outside_custom_byte_range_is_rejected(self, pnum):
        store = _store()
        with pytest.raises(ValueError, match="custom pnum"):
            await store.async_save("Bad", [(2, 60)], pnum)
        store._store.async_save.assert_not_awaited()

    async def test_empty_name_is_rejected(self):
        with pytest.raises(ValueError, match="name must not be empty"):
            await _store().async_save(" ", [(2, 60)])

    async def test_overwriting_keeps_number_and_names_are_trimmed(self):
        store = _store()
        await store.async_save("First", [(2, 60)], 123)
        await store.async_save(" Updated ", [(3, 90)], 123)
        assert store.list() == {123: {"name": "Updated", "steps": [(3, 90)]}}

    async def test_returned_values_do_not_mutate_store(self):
        store = _store()
        await store.async_save("First", [(2, 60)])
        copy = store.list()
        copy[120]["steps"].append((4, 90))
        store.get(120)["steps"].append((4, 90))
        assert store.get(120)["steps"] == [(2, 60)]


class TestCustomSchemeSelect:
    async def test_selection_sends_custom_steps(self):
        entity = _make_entity("OCLEANY3P", active_pnum=120)
        store = _store()
        await store.async_save("My programme", [(2, 90), (3, 90)])
        entity.coordinator.hass.data = {DOMAIN: {"_programs": store}}
        entity.coordinator.async_set_custom_scheme = AsyncMock()
        entity.async_write_ha_state = MagicMock()
        assert "My programme" in entity.options
        assert entity.current_option == "My programme"
        await entity.async_select_option("My programme")
        entity.coordinator.async_set_custom_scheme.assert_awaited_once_with(120, [(2, 90), (3, 90)])
        assert entity.extra_state_attributes["programs"][120]["kind"] == "custom"


class TestCustomProgramServices:
    async def test_services_save_select_and_delete_shared_programme(self):
        hass = _make_hass()
        entry = _make_entry()
        coord = _make_coordinator(hass=hass)
        coord.async_refresh = AsyncMock()
        coord.async_set_custom_scheme = AsyncMock()
        with (
            patch("custom_components.oclean_ble._attach_file_handler", AsyncMock()),
            patch("custom_components.oclean_ble.OcleanCoordinator", return_value=coord),
        ):
            await async_setup_entry(hass, entry)
        for task in entry.background_tasks:
            await task
        services = {c.args[1]: c.args[2] for c in hass.services.async_register.call_args_list}
        await services["set_custom_scheme"](
            MagicMock(data={"entry_id": entry.entry_id, "pnum": 120, "steps": [{"gear": 2, "duration": 180}]})
        )
        coord.async_set_custom_scheme.assert_awaited_once_with(120, [(2, 180)])
        with pytest.raises(ServiceValidationError, match="No Oclean device"):
            await services["set_custom_scheme"](
                MagicMock(data={"entry_id": "missing", "pnum": 120, "steps": [{"gear": 2, "duration": 180}]})
            )
        coord._zone_history = [{"ts": 1700000000, "zones": [15] * 8}, {"ts": 1700000300, "zones": [20] * 8}]
        history = await services["get_zone_history"](MagicMock(data={"entry_id": entry.entry_id}))
        assert [s["ts"] for s in history["sessions"]] == [1700000300, 1700000000]
        history = await services["get_zone_history"](
            MagicMock(data={"entry_id": entry.entry_id, "start": "2023-11-14T22:15:00+00:00"})
        )
        assert [s["ts"] for s in history["sessions"]] == [1700000300]
        saved = await services["save_custom_program"](
            MagicMock(data={"name": "Evening", "steps": [{"gear": 2, "duration": 180}]})
        )
        assert saved == {"pnum": 120}
        assert hass.data[DOMAIN]["_programs"].get(120)["steps"] == [(2, 180)]
        await services["delete_custom_program"](MagicMock(data={"pnum": 120}))
        assert hass.data[DOMAIN]["_programs"].get(120) is None
        with pytest.raises(ServiceValidationError, match="custom pnum"):
            await services["save_custom_program"](
                MagicMock(data={"name": "Bad", "pnum": 256, "steps": [{"gear": 2, "duration": 180}]})
            )


class TestCustomProgrammeWrite:
    async def test_eight_steps_split_into_valid_ble_packets_and_persist_selection(self):
        coord = _make_coordinator()
        client = _make_bleak_client()
        coord._store.async_save = AsyncMock()
        steps = [(16, 20)] * 8
        with (
            patch("custom_components.oclean_ble.coordinator.establish_connection", AsyncMock(return_value=client)),
            patch.object(coord, "_resolve_ble_device", return_value=MagicMock()),
            patch("custom_components.oclean_ble.coordinator.asyncio.sleep", AsyncMock()),
        ):
            await coord.async_set_custom_scheme(120, steps)
        packets = [c.args[1] for c in client.write_gatt_char.await_args_list]
        assert len(packets) == 2
        assert all(len(p) <= 20 for p in packets)
        assert packets[0][:2] == bytes.fromhex("0206")
        assert coord.active_scheme_pnum == 120
        assert coord._store.async_save.await_args.args[0]["active_scheme_pnum"] == 120
        client.disconnect.assert_awaited_once()

    async def test_invalid_steps_never_connect_to_brush(self):
        coord = _make_coordinator()
        with (
            patch("custom_components.oclean_ble.coordinator.establish_connection", AsyncMock()) as connect,
            pytest.raises(ValueError, match="too many steps"),
        ):
            await coord.async_set_custom_scheme(120, [(16, 20)] * 9)
        connect.assert_not_awaited()

"""Regression tests for Elite Pro packet loss, persistence and session features."""

from __future__ import annotations

import asyncio
import datetime
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.oclean_ble.const import (
    DATA_BATTERY,
    DATA_LAST_BRUSH_AREAS,
    DATA_LAST_BRUSH_DURATION,
    DATA_LAST_BRUSH_DURATION_SCHEDULED,
    DATA_LAST_BRUSH_SCORE,
    DATA_LAST_BRUSH_TIME,
    DATA_MODEL_ID,
    DATA_SW_VERSION,
    EVENT_BRUSH_SESSION,
    READ_NOTIFY_CHAR_UUID,
    RECEIVE_BRUSH_UUID,
    TOOTH_AREA_NAMES,
)
from custom_components.oclean_ble.coordinator import _valid_session_timestamp
from custom_components.oclean_ble.parser import parse_t1_c3352g_record
from tests.test_coordinator import (
    _make_bleak_client,
    _make_c3352g_record_bytes,
    _make_coordinator,
    _make_t1_c3352g_packets,
)

# Two adjacent real-device records whose zone bytes become 2032-12-25 / 777 s
# when a 20-byte continuation packet is lost. Contains no device identifier.
_REAL_RECORD = bytes.fromhex("1a0a031502350000b4007908000b1e000010001f200c190c130d130309080e00005b00ffffffffffffff")
_NEXT_RECORD = bytes.fromhex("1a0a040a381d0000b400b209000f1c000010001c1d15160b0e0f0e060f080e00006400ffffffffffffff")


def _receiver(coordinator=None):
    coordinator = coordinator or _make_coordinator()
    collected = {DATA_MODEL_ID: "OCLEANY3P"}
    sessions = []
    handler, flush = coordinator._make_notification_handler(collected, sessions, set(), asyncio.Event())
    return collected, sessions, handler, flush


class TestTransferIntegrity:
    def test_lost_packet_reproduces_2032_but_transfer_is_rejected(self):
        packets = _make_t1_c3352g_packets([_make_c3352g_record_bytes(), _REAL_RECORD, _NEXT_RECORD])
        del packets[1]
        shifted = packets[0][7:] + b"".join(packets[1:])
        decoded = parse_t1_c3352g_record(shifted[42:84])
        assert datetime.datetime.fromtimestamp(decoded[DATA_LAST_BRUSH_TIME]) == datetime.datetime(
            2032, 12, 25, 12, 19, 13
        )
        assert decoded[DATA_LAST_BRUSH_DURATION] == 777
        collected, sessions, handler, flush = _receiver()
        for packet in packets:
            handler(RECEIVE_BRUSH_UUID, bytearray(packet))
        flush()
        assert sessions == []
        assert DATA_LAST_BRUSH_TIME not in collected

    @pytest.mark.parametrize("drop_index", range(1, 7))
    def test_loss_in_middle_or_tail_never_updates_session(self, drop_index):
        packets = _make_t1_c3352g_packets([_REAL_RECORD, _NEXT_RECORD, _NEXT_RECORD])
        del packets[drop_index]
        collected, sessions, handler, flush = _receiver()
        for packet in packets:
            handler(RECEIVE_BRUSH_UUID, bytearray(packet))
        flush()
        assert sessions == []
        assert DATA_LAST_BRUSH_DURATION not in collected

    def test_padding_is_not_a_session(self):
        packets = _make_t1_c3352g_packets([_REAL_RECORD, _NEXT_RECORD])
        packets[-1] += b"\0" * (20 - len(packets[-1]))
        collected, sessions, handler, flush = _receiver()
        for packet in packets:
            handler(RECEIVE_BRUSH_UUID, bytearray(packet))
        flush()
        assert len(sessions) == 2
        assert collected[DATA_LAST_BRUSH_DURATION] == 178

    def test_whole_packet_overflow_rejects_transfer(self):
        packets = _make_t1_c3352g_packets([_REAL_RECORD])
        packets[-1] += b"\x03" * 20
        collected, sessions, handler, _ = _receiver()
        for packet in packets:
            handler(RECEIVE_BRUSH_UUID, bytearray(packet))
        assert sessions == []
        assert DATA_LAST_BRUSH_TIME not in collected

    def test_future_record_rejects_whole_complete_transfer(self):
        packets = _make_t1_c3352g_packets([_REAL_RECORD, _make_c3352g_record_bytes(year=2032)])
        collected, sessions, handler, _ = _receiver()
        for packet in packets:
            handler(RECEIVE_BRUSH_UUID, bytearray(packet))
        assert sessions == []
        assert DATA_LAST_BRUSH_TIME not in collected

    def test_other_characteristic_cannot_corrupt_stream(self):
        collected, sessions, handler, flush = _receiver()
        packets = _make_t1_c3352g_packets([_REAL_RECORD])
        handler(SimpleNamespace(uuid=RECEIVE_BRUSH_UUID), bytearray(packets[0]))
        handler(SimpleNamespace(uuid=READ_NOTIFY_CHAR_UUID), bytearray.fromhex("030364"))
        for packet in packets[1:]:
            handler(SimpleNamespace(uuid=RECEIVE_BRUSH_UUID), bytearray(packet))
        flush()
        assert len(sessions) == 1
        assert collected[DATA_LAST_BRUSH_DURATION] == 121

    def test_new_header_recovers_after_timeout_and_ignores_late_tail(self):
        collected, sessions, handler, flush = _receiver()
        packets = _make_t1_c3352g_packets([_REAL_RECORD])
        handler(RECEIVE_BRUSH_UUID, bytearray(packets[0]))
        flush()
        handler(RECEIVE_BRUSH_UUID, bytearray(packets[1]))
        assert sessions == []
        for packet in packets:
            handler(RECEIVE_BRUSH_UUID, bytearray(packet))
        assert len(sessions) == 1
        assert collected[DATA_LAST_BRUSH_DURATION] == 121

    def test_new_header_abandons_incomplete_previous_burst(self):
        collected, sessions, handler, _ = _receiver()
        packets = _make_t1_c3352g_packets([_REAL_RECORD])
        handler(RECEIVE_BRUSH_UUID, bytearray(packets[0]))
        for packet in packets:
            handler(RECEIVE_BRUSH_UUID, bytearray(packet))
        assert len(sessions) == 1
        assert collected[DATA_LAST_BRUSH_DURATION] == 121

    def test_future_inline_notification_is_rejected(self):
        collected, sessions, handler, _ = _receiver()
        handler(READ_NOTIFY_CHAR_UUID, bytearray.fromhex("03072a42230000200c190c130d0003090309"))
        assert sessions == []
        assert DATA_LAST_BRUSH_TIME not in collected


class TestStoredSessionRecovery:
    async def test_load_repairs_poisoned_snapshot_and_both_cursors(self):
        coord = _make_coordinator()
        future = int(time.time()) + 6 * 365 * 86400
        coord._store.async_load = AsyncMock(
            return_value={
                "last_session_ts": future,
                "last_processed_session_ts": future,
                "last_session": {
                    DATA_LAST_BRUSH_TIME: future,
                    DATA_LAST_BRUSH_DURATION: 777,
                    DATA_LAST_BRUSH_SCORE: 9,
                    DATA_BATTERY: 92,
                    DATA_MODEL_ID: "OCLEANY3P",
                },
                "session_group": {"start_ts": future},
                "zone_history": [{"ts": future}, {"ts": 1700000000}],
                "area_remind": True,
                "active_scheme_pnum": 120,
            }
        )
        coord._store.async_save = AsyncMock()
        await coord._load_store()
        assert coord._last_session_ts == 0
        assert coord._last_processed_session_ts == 0
        assert DATA_LAST_BRUSH_TIME not in coord._last_raw
        assert DATA_LAST_BRUSH_DURATION not in coord._last_raw
        assert coord._last_raw[DATA_BATTERY] == 92
        assert coord._last_raw[DATA_MODEL_ID] == "OCLEANY3P"
        assert coord._active_scheme_pnum == 120
        assert coord._area_remind is True
        assert coord._session_group is None
        assert coord._zone_history == [{"ts": 1700000000}]
        coord._store.async_save.assert_awaited_once()
        saved = coord._store.async_save.call_args.args[0]
        assert saved["last_session_ts"] == 0

    async def test_valid_snapshot_survives_repair(self):
        coord = _make_coordinator()
        coord._last_raw = {DATA_LAST_BRUSH_TIME: 1700000000, DATA_LAST_BRUSH_DURATION: 120}
        coord._last_session_ts = 1700000000
        assert coord._repair_session_state() is False
        assert coord._last_raw[DATA_LAST_BRUSH_DURATION] == 120

    @pytest.mark.parametrize("value", [None, True, "2032", float("nan"), float("inf"), -1])
    def test_invalid_timestamp_types_are_rejected(self, value):
        assert _valid_session_timestamp(value) is False

    def test_timezone_skew_is_tolerated(self):
        assert _valid_session_timestamp(int(time.time()) + 14 * 3600) is True
        assert _valid_session_timestamp(int(time.time()) + 2 * 86400) is False


class TestSessionFeatureDeduplication:
    async def test_events_history_and_groups_do_not_repeat_without_recorder(self):
        coord = _make_coordinator()
        coord._merge_window_s = 60
        coord._zone_history_days = -1
        start = int(time.time()) - 3600
        sessions = [
            {
                DATA_LAST_BRUSH_TIME: start + offset,
                DATA_LAST_BRUSH_DURATION: 120,
                DATA_LAST_BRUSH_DURATION_SCHEDULED: 180,
                DATA_LAST_BRUSH_SCORE: 50,
                DATA_LAST_BRUSH_AREAS: dict.fromkeys(TOOTH_AREA_NAMES, 15),
            }
            for offset in [0, 150]
        ]

        async def setup(_client, collected):
            collected.update(sessions[-1])
            collected[DATA_MODEL_ID] = "OCLEANY3P"
            return [dict(s) for s in sessions]

        with (
            patch.object(coord, "_resolve_ble_device", return_value=MagicMock()),
            patch(
                "custom_components.oclean_ble.coordinator.establish_connection",
                AsyncMock(return_value=_make_bleak_client()),
            ),
            patch.object(coord, "_setup_and_read", side_effect=setup),
            patch("custom_components.oclean_ble.coordinator.import_new_sessions", AsyncMock(return_value=0)),
        ):
            await coord._poll_device()
            await coord._poll_device()
        assert coord.hass.bus.async_fire.call_count == 2
        assert all(c.args[0] == EVENT_BRUSH_SESSION for c in coord.hass.bus.async_fire.call_args_list)
        assert coord.group_duration == 240
        assert coord.group_score == 100
        assert len(coord.zone_history) == 2
        assert coord._brush_head_sw_count == 2
        assert coord._last_session_ts == 0
        assert coord._last_processed_session_ts == start + 150
        event = coord.hass.bus.async_fire.call_args.args[1]
        assert event["group_continuation"] is True
        assert event["group_size"] == 2
        assert event["zones"] == [15] * 8
        assert event["zones_emoji"] is not None

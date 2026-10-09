# Oclean Toothbrush – kamkilt fork for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Fork](https://img.shields.io/badge/fork-kamkilt-blue)](https://github.com/kamkilt/ha-oclean-integration)
[![Version](https://img.shields.io/badge/version-1.4.1-green)](custom_components/oclean_ble/manifest.json)
[![License](https://img.shields.io/github/license/kamkilt/ha-oclean-integration)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/kamkilt/ha-oclean-integration/tests.yaml?label=tests)](https://github.com/kamkilt/ha-oclean-integration/actions)
[![hassfest](https://img.shields.io/github/actions/workflow/status/kamkilt/ha-oclean-integration/hassfest.yaml?label=hassfest)](https://github.com/kamkilt/ha-oclean-integration/actions/workflows/hassfest.yaml)
[![validate](https://img.shields.io/github/actions/workflow/status/kamkilt/ha-oclean-integration/validate.yaml?label=validate)](https://github.com/kamkilt/ha-oclean-integration/actions/workflows/validate.yaml)

> **Unofficial community integration.** This project is not affiliated with, endorsed by,
> or connected to Oclean / Zhuhai Ice Bear Smart Home Technology Co., Ltd.
> "Oclean" is a registered trademark of its respective owner.

Custom integration for **Oclean Smart Toothbrushes** (Oclean X, X Pro, X Pro Elite, and compatible models).

Connects every 5 minutes via Bluetooth, reads brushing data, then disconnects.
No cloud, no account, fully local.

> **Devices tested:** Oclean X (OCLEANY3M) · Oclean X HW variant (OCLEANY3MH) · Oclean X Pro (OCLEANY3) · Oclean X Pro Elite (OCLEANY3P) · Oclean X Pro 20 (OCLEANX20) · Oclean X Ultra (OCLEANV1a) · Oclean Z1 (OCLEANY5) · Oclean Air 1 (OCLEANA1)
> **Protocol:** Reverse-engineered from the official Oclean APK

---

## This fork (v1.4.1)

**This is [kamkilt’s fork](https://github.com/kamkilt/ha-oclean-integration).**
Home Assistant and HACS display **Oclean Toothbrush (kamkilt fork)**. The options
window shows **kamkilt fork v1.4.1**, and the startup log includes the fork name
and installed version, making the installed build easy to identify.

**To jest fork kamkilt.** W HASS szukaj nazwy **Oclean Toothbrush (kamkilt fork)**;
w oknie konfiguracji zobaczysz również wersję **1.4.1**. Aktualizacja istniejącej
instalacji: podmień cały katalog `/config/custom_components/oclean_ble/`, uruchom
ponownie Home Assistant i użyj przycisku **Update Now** przy obudzonej szczoteczce.
Zachowaj obecną konfigurację integracji. Łączenie sesji oraz historię stref włącz
w jej opcjach; domyślnie są wyłączone. W HACS dodaj repozytorium **kamkilt**, aby
kolejne aktualizacje pochodziły z tego forka.

Based on [deniskie’s integration](https://github.com/deniskie/ha-oclean-integration),
with packet-loss recovery for Elite Pro / ESPHome Bluetooth proxies and
[PPP01’s feature work](https://github.com/PPP01/ha-oclean-integration): coverage
image, named custom programmes, brushing events, session merging and zone history.
The feature commits were adapted to the current upstream version.

Incomplete multi-record `*B#` transfers are discarded. Previously a missing
20-byte notification shifted record boundaries; replaying captured Elite Pro
bytes reproduced a fictitious **2032-12-25 / 777 s** session. Complete transfers
are now checked before any record is accepted, and independent Bluetooth
characteristics have separate roles during reassembly. Invalid future session
cursors and cached snapshots are cleared automatically on loading or polling,
while device settings are preserved. A one-day timestamp tolerance accommodates
existing device timezone differences. A later successful poll restores the data.
The captured logs establish the decoding failure; they do not establish whether
the original packet loss happened in the brush, radio link or proxy.

## Installation

### Option A – HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Click **⋮ → Custom repositories**.
3. Add `https://github.com/kamkilt/ha-oclean-integration` as **Integration**.
4. Search for **Oclean** and install.
5. Restart Home Assistant.

### Option B – Manual

1. Download or clone this repository.
2. Copy the `custom_components/oclean_ble/` folder to your HA config directory:
   ```
   /config/custom_components/oclean_ble/
   ```
3. Restart Home Assistant.

### Updating an existing installation

Replace the **entire** `custom_components/oclean_ble/` folder and restart Home
Assistant. Keep the existing Oclean configuration entry. After restart, press
**Update Now** with the toothbrush awake and close to the Bluetooth proxy.
Replacing only the coordinator or image file will miss dependencies of the new
features. Old erroneous rows already recorded by Home Assistant are not removed
by this update; the integration repairs its own state and subsequent readings.

### Setup

After restart, go to **Settings → Integrations → Add Integration** and search for **Oclean**.

- If your brush is turned on and nearby, it may be **auto-discovered** via Bluetooth.
- Otherwise, enter the **MAC address** manually (found in the official Oclean app under device settings).

---

## Added features

### Coverage image

Each device has an `image` entity named **Brush Coverage**, with upper and lower
jaws and separate inner/outer tooth surfaces. Add it to a dashboard with a
picture-entity card (replace the example entity ID with your device’s entity):

```yaml
type: picture-entity
entity: image.oclean_brush_coverage
show_name: true
show_state: false
```

Colours show each zone’s contribution relative to the session average: green
at least 75 %, orange at least 40 %, red above zero, grey zero. These are relative
zone ratings; a uniformly short brushing session can still show green. The
**Duration Rating** sensor reports whether the programme duration was reached.
An image requires zone data supplied by the brush.

### Named custom programmes

Use **Developer tools → Actions → Oclean: Save custom programme** to create a
programme shared by all configured toothbrushes. Up to **eight** steps are
supported. Each has a gear (1–32 clean, 33–36 whitening, 37–40 massage, 41 extended)
and a duration of 1–255 seconds. For example, this stores a 180-second programme:

```yaml
action: oclean_ble.save_custom_program
data:
  name: My 3-minute programme
  steps:
    - gear: 16
      duration: 90
    - gear: 20
      duration: 90
```

Select it in the device’s **Brush Scheme** dropdown to send it to the brush. The
save action can return its `pnum` when called with a response variable; allocated
custom slots are 120–255. Delete a saved programme with
`oclean_ble.delete_custom_program`, passing that `pnum`. This removes it from the
Home Assistant catalogue. `oclean_ble.set_custom_scheme` can also send a step
list directly to one device using `entry_id`, `pnum` (0–255) and `steps`.
Programme support and persistence depend on the brush firmware; saving a name
in Home Assistant is separate from writing it to a toothbrush.

### Brushing events for automations

Every newly received session fires `oclean_ble_brush_session` once, including
older sessions received together in one poll. Event fields include `entry_id`,
`mac`, `device_name`, `ts`, `duration`, `duration_scheduled`, `score`, `pnum`,
`zones`, `zones_emoji`, `group_continuation` and `group_size`. Times and durations
are in seconds; `ts` is the session timestamp, which may be historical.
For example, an automation can listen with:

```yaml
triggers:
  - trigger: event
    event_type: oclean_ble_brush_session
    event_data:
      entry_id: YOUR_OCLEAN_CONFIG_ENTRY_ID
```

Repeated polls do not repeat events. Events and history keep a separate
persisted cursor from Home Assistant statistics, so a disabled recorder does
not create duplicate events.

### Merge consecutive sessions

In **Settings → Devices & services → Oclean → Configure**, set **Merge sessions**
to 1–5 minutes (default 0, disabled). A second session starting within that gap
from the preceding session’s end joins the group. The extra **Merged duration**
sensor sums actual durations; **Merged score** sums individual firmware scores
and caps the result at 100 %. This is an integration calculation, not a score
recomputed by the Oclean firmware. Individual session readings remain available.

### Zone history

In the same options, enable **Zone history** with retention of 30, 60, 90, 180
or 365 days, or unlimited (default off). New sessions with zone data are stored
locally with timestamp, eight zone values, duration, score and programme number.
Enabling history does not reimport sessions already processed by this installation.
The action `oclean_ble.get_zone_history` returns sessions newest first and
supports optional `start` / `end` date filters. To use its response in a script:

```yaml
sequence:
  - action: oclean_ble.get_zone_history
    data:
      entry_id: YOUR_OCLEAN_CONFIG_ENTRY_ID
    response_variable: brushing_history
```

---

## Entities

Entity IDs follow the pattern `<platform>.<device_name>_<suffix>` where `<device_name>` is the name you gave the device during setup (default: `oclean`).

### Sensors

#### Session data – updated after each brushing session

| Name | Suffix | Description | Unit | Status |
|------|--------|-------------|------|--------|
| Battery | `_battery` | Current battery level | % | ✅ Tested |
| Last Session | `_last_session` | Timestamp of the last brushing session | timestamp | ✅ Tested |
| Score | `_score` | Brushing quality score of the last session (0–100) | – | ✅ Tested |
| Duration | `_duration` | **Actual** brushing time of the last session (not the programme length). The scheduled programme length is exposed as the `scheduled_duration_s` attribute | s (displayed as min) | ✅ Tested |
| Last Scheme | `_last_scheme` | Brushing programme used in the last session – human-readable name (e.g. "Clean", "Sensitive") from the pNum lookup table; falls back to the raw number if unknown | – | ✅ Tested |
| Pressure | `_pressure` | Average brushing pressure across all tooth zones in the last session (raw ADC value 0–255) | – | ⚠️ Unconfirmed |
| Coverage | `_coverage` | Percentage of tooth zones adequately cleaned in the last session (0–100 %). Uses the official Oclean app threshold: zones with raw pressure > 100 count as covered. | % | ✅ Tested |
| Duration Rating | `_duration_rating` | Actual duration relative to the programme length recorded in that session: `min(100, actual / scheduled × 100)`. Falls back to 240 s only when the device does not provide a programme length | % | ⚠️ Unconfirmed |
| Gesture | `_gesture` | Brushing technique indicator from the device (raw value 0–255 from byte 14 of 42-byte session records) | – | ⚠️ Unconfirmed |
| Pressure Detail | `_pressure_detail` | Average of the 5-segment pressure ratio from 42-byte session records. Per-segment values available as entity attributes (`segment_1` … `segment_5`) | – | ⚠️ Unconfirmed |
| Power Distribution | `_power_distribution` | Number of zones with power > 0 from per-zone power levels (0–3 scale). Per-zone values available as entity attributes (mapped to tooth area names), plus `gesture_array` | – | ⚠️ Unconfirmed |
| Cleaned Zones | `_cleaned_zones` | Number of tooth zones (0–8) with non-zero pressure in the last session; individual per-zone pressures available as entity attributes | – | ⚠️ Unconfirmed |
| Zone \<name\> | `_zone_<name>` | Pressure for one individual tooth zone in the last session (raw value 0–255; 0 = not brushed / no data). Eight sensors, one per zone: `upper_left_out`, `upper_left_in`, `lower_left_out`, `lower_left_in`, `upper_right_out`, `upper_right_in`, `lower_right_out`, `lower_right_in` | – | ⚠️ Unconfirmed |

#### Device settings – updated every poll from the device

| Name | Suffix | Description | Unit | Status |
|------|--------|-------------|------|--------|
| Mode | `_mode` | Active brushing mode currently set on the device (`modeNum` from 0302 response, byte 5). Device-family-specific integer – e.g. 1 = Standard, 2 = Sensitive; exact mapping varies by model. Unlike "Last Scheme", this reflects the device's current configuration, not the last session. | – | ⚠️ Unconfirmed |
| Head Sessions | `_head_sessions` | Number of brushing sessions since the last brush head reset (`headUsedTimes` from 0302 response) | – | ⚠️ Unconfirmed |
| Head Age | `_head_age` | Calendar days elapsed since the last brush head reset (`headUsedDays` from 0302 response) | d | ⚠️ Unconfirmed |

#### Diagnostic – device information, always shown

| Name | Suffix | Description | Unit | Status |
|------|--------|-------------|------|--------|
| Model | `_model` | Device model ID from BLE Device Information Service (e.g. `OCLEANY3M`) | – | ✅ Tested |
| Firmware | `_firmware` | Firmware version string from BLE DIS (e.g. `1.0.0.20`) | – | ✅ Tested |
| HW Revision | `_hw_revision` | Hardware revision string from BLE DIS (e.g. `Rev.D`) | – | ✅ Tested |
| MAC Address | `_mac_address` | Bluetooth MAC address of the device | – | ✅ Tested |
| Last Poll | `_last_poll` | Timestamp of the last completed BLE poll | timestamp | ✅ Tested |
| Signal strength | `_signal_strength` | Advertisement RSSI, read from HA's Bluetooth registry rather than a BLE poll, so it stays available between polls and while the brush is asleep. The `by_scanner` attribute lists the RSSI seen by each adapter/proxy | dBm | ✅ Tested |

### Switches

| Name | Suffix | Description | Status |
|------|--------|-------------|--------|
| Area Reminder | `_area_reminder` | Enables/disables the tooth-zone completion reminder on the device (writes CMD 020D; state persisted locally – assumes state, no read-back) | ⚠️ Unconfirmed |
| Over-Pressure Alert | `_over_pressure` | Enables/disables the brushing over-pressure alert on the device (writes CMD 0212; state persisted locally – assumes state, no read-back) | ⚠️ Unconfirmed |
| Brushing Reminder | `_brushing_reminder` | Enables/disables the brushing reminder on the device (writes CMD 0239; state persisted locally – assumes state, no read-back) | ⚠️ Unconfirmed |
| Auto Power-Off Timer | `_auto_power_off_timer` | Enables/disables the automatic power-off timer on the device (writes CMD 0240; state persisted locally – assumes state, no read-back) | ⚠️ Unconfirmed |

### Numbers

| Name | Suffix | Description | Unit | Status |
|------|--------|-------------|------|--------|
| Brush Head Lifetime | `_brush_head_lifetime` | Maximum brush head lifetime in days. When "Head Age" or "Head Sessions" exceeds this value, a replacement reminder is shown in HA (writes CMD 0217; state persisted locally) | d | ⚠️ Unconfirmed |

### Buttons

| Name | Suffix | Description | Status |
|------|--------|-------------|--------|
| Reset Brush Head | `_reset_brush_head` | Resets the brush head wear counter on the device (CMD 020F) and clears the local session counter | ⚠️ Unconfirmed |
| Sync Time | `_sync_time` | Synchronises the current time to the device clock | ✅ Tested |
| Update Now | `_update_now` | Triggers an immediate BLE poll (same as the `oclean_ble.poll` action) | ✅ Tested |

**Legend:**
- ✅ **Tested** – confirmed working on real hardware with multiple sessions
- ⚠️ **Unconfirmed** – implemented based on APK reverse-engineering; needs more device testing
- ❌ **Not implemented** – see [Roadmap](#roadmap)

---

## Feature Status

### ✅ Confirmed Working

| Feature | Details |
|---------|---------|
| Bluetooth connection | Automatic reconnect at each poll interval |
| Battery level | Read directly from device |
| Last brush score | Confirmed with multiple real sessions (Oclean X); delivered via separate BLE notification after session end |
| Last brush timestamp | Device local time, confirmed across multiple sessions |
| Last brush duration | Session length; displayed in minutes by default (e.g. 2.5 min). Confirmed on Oclean X (0307 format, APK-verified via AbstractC0002b.m18f) |
| Last brush scheme type | Brush programme name/ID (pNum); confirmed on Oclean X via 0307 (APK-verified) |
| Time calibration | Device clock synced on every poll and on demand via the *Sync Time* button |
| Poll interval | Configurable 60–86400 seconds (default: 300 s), or set to `0` for manual-only mode |
| Stale data persistence | Sensors keep last known value when device is unreachable |
| Config flow | Manual MAC address entry with validation |
| Duplicate prevention | Sessions deduplicated by timestamp; no double-import |
| Device info | Model, firmware version, and hardware revision read from standard BLE Device Information Service (0x180A); shown in HA device info panel and as diagnostic sensors |

### ⚠️ Implemented – Needs More Testing

| Feature | Details |
|---------|---------|
| Brush head usage counter | Resets when the "Reset Brush Head" button is pressed |
| Last brush pressure | Average brushing pressure across all tooth zones (extended 0308 format only) |
| Last brush areas | Pressure per tooth zone; individual zones as entity attributes and as 8 dedicated sensors. Source: `2604` notifications on Type-1 devices (Oclean X series) or extended 0308 format on Type-0 devices |
| Duration rating | Actual brushing duration divided by the session’s scheduled programme duration, capped at 100 % (240 s fallback when unavailable) |
| Brushing quality metrics | Gesture code, 5-segment pressure ratio, and per-zone power distribution (0–3 scale) from 42-byte session records; exposed as sensors with detail attributes |
| Feature toggle switches | Brushing Reminder (CMD 0239) and Auto Power-Off Timer (CMD 0240); state persisted locally |
| Brush head reset button | Sends reset command to device; no response verification yet |
| Session history pagination | Fetches multiple pages of session history from device |
| Offline session import | Sessions recorded while HA was unreachable are imported on the next poll, provided they are still in the device's buffer. Note: the official Oclean app likely clears the buffer on sync – for best results, avoid using the official app in parallel. |
| HA long-term statistics | Sessions imported with their actual timestamps (historical data support) |
| Bluetooth auto-discovery | Device is found automatically if visible to HA Bluetooth |
| Older device protocol | Two data formats implemented; not yet tested on real non-X hardware |
| Multiple brushes in one household | Each brush is a separate config entry; not yet tested with multiple devices |

### ❌ Not Planned

| Feature | Details |
|---------|---------|
| Active-brushing detection | Removed in v1.3.0. The 0303 STATE byte correctly reports brushing status, but the device does not push BLE data during brushing and the polling interval is too long to catch the ~2–3 min brushing window reliably. |

---

## Configuration

The poll interval and other options can be changed after setup via **Settings → Integrations → Oclean → Configure**.

### Manual Polling Mode

Set the poll interval to `0` in **Settings → Integrations → Oclean → Configure** to disable automatic polling entirely. In this mode the device is only contacted when you explicitly trigger a poll.

Use the built-in `oclean_ble.poll` action to trigger a poll on demand – from automations, scripts, or the HA Developer Tools:

```yaml
action: oclean_ble.poll
data: {}             # polls all Oclean devices
```

To target a single device when you have multiple brushes, pass its `entry_id` (found under **Settings → Integrations → Oclean → ⋮ → System Information**):

```yaml
action: oclean_ble.poll
data:
  entry_id: "abc123def456..."
```

This is useful for event-driven automations, for example polling immediately after a bed-occupancy sensor detects you went to sleep:

```yaml
automation:
  trigger:
    - platform: state
      entity_id: binary_sensor.bed_occupancy
      to: "on"
  action:
    - action: oclean_ble.poll
      data: {}
```

The `oclean_ble.poll` action is also available when automatic polling is active – it simply triggers an immediate poll in addition to the regular schedule.

### Post-Brush Cooldown

After a new session is detected, polling can be paused for a configurable number of hours. This avoids unnecessary Bluetooth connections immediately after brushing, when no new data is expected.

Set the cooldown duration (in hours) in **Settings → Integrations → Oclean → Configure**. The default is `0` (disabled).

### Poll Windows

You can restrict polling to specific time windows to reduce Bluetooth traffic outside brushing hours. The options flow guides you step-by-step through up to 3 time windows (e.g. morning and evening) using a native time picker.

When no windows are configured, the device is polled at every interval.

### Debug Logging

Debug logging is **opt-in**. While it is disabled, the integration writes nothing to disk — warnings and errors still go to the main HA log (Settings → Logs) as usual. This keeps raw BLE payloads, session scores and your device MAC out of the config directory (and therefore out of your backups) unless you ask for them.

**Enable it one of two ways:**

*Option A – UI (no restart):* Settings → Devices & Services → Oclean → ⋮ → **Enable debug logging**. Home Assistant reloads the integration automatically.

*Option B – `configuration.yaml`:*

```yaml
logger:
  default: warning
  logs:
    custom_components.oclean_ble: debug
```

Then restart Home Assistant, or reload the Oclean integration.

Once enabled, the integration writes a dedicated log file `oclean_ble.log` next to your `configuration.yaml` (e.g. `/config/oclean_ble.log`), in addition to the main HA log. The file rotates at 1 MB and keeps up to 3 files.

To stop writing the file again, turn debug logging back off and reload the integration (or restart HA). The existing `oclean_ble.log` is not deleted — remove it manually if you no longer want it.

After brushing, filter the log for `Oclean` to see raw Bluetooth payloads.
Unknown notification types are logged as hex – this helps extend the parser.

---

## Compatibility

| Device | Model ID | Status | Notes |
|--------|----------|--------|-------|
| Oclean X | OCLEANY3M | ✅ Tested | Battery, score, timestamp, duration, and scheme ID confirmed. Extended fields (areas, pressure) not supported by this device. |
| Oclean X (HW variant) | OCLEANY3MH | ✅ Tested | Score, timestamp, duration, and pNum confirmed via `XX03` notification format (issue #19). |
| Oclean X Pro | OCLEANY3 | ⚠️ Partial | Session data fetched via `0307` + `*B#` multi-packet reassembly; implementation complete but needs real-device confirmation. |
| Oclean X Pro Elite | OCLEANY3P | ⚠️ Partial | Session metadata via `5100`, tooth areas via `021f`; implementation complete, full field confirmation pending. |
| Oclean X Pro 20 | OCLEANX20 | ⚠️ Partial | Extended-offset inline `0307` format; timestamp and duration confirmed, further field testing pending. |
| Oclean Z1 | OCLEANY5 | ⚠️ Partial | Type-Z1 protocol (APK handler C3350f mode=1): 0303/0202/0302 via fbb85, 0307 via fbb89, notify on fbb86+fbb90. Time calibration uses 0201 + 8-byte datetime format. Implementation complete (issue #69), real-device confirmation pending. |
| Oclean Air 1 | OCLEANA1 | ✅ Tested | Battery confirmed. No CCCD on notify characteristic – uses direct READ fallback. Session fields not available on this model. |
| Oclean Air 1 variants | OCLEANA1a–d | ⚠️ Partial | Same protocol as OCLEANA1; untested on real hardware. |
| Oclean X Ultra | OCLEANV1a | ⚠️ Partial | Battery, timestamp, duration, programme confirmed. Score and tooth areas pending (issue #81). |
| Oclean X Ultra 20 | OCLEANV20 | ⚠️ Partial | Mapped to Type-1 as the same Ultra family as OCLEANV1a; no device log yet (issue #134). |
| Oclean X Pro Elite (X) | OCLEANY3X | ⚠️ Partial | Same product as OCLEANY3P per the reporter; mapped to Type-1 (issue #110). |
| Oclean SE | OCLEANY2 | ⚠️ Partial | APK handler `C3391z0` uses the Type-1 characteristics (0303/0202/0302 via fbb85, 0307 via fbb89). Firmware below 1.0.0.4 would need `0306` instead of `0307` and is not supported (issue #141). |
| Other Oclean models | – | ⚠️ Unknown | Open an issue with raw log output |

> If brush session detail fields (areas, pressure, scheme) are missing or the timestamp looks wrong, enable debug logging, brush your teeth, and open an issue with the raw hex output from the HA log.

> If your device is not listed, enable debug logging and open an issue with the raw hex output. This is how Oclean X support was developed.

---

## Roadmap

- [ ] Confirm brush area / pressure / scheme fields on Oclean X Pro (OCLEANY3) and X Pro Elite (OCLEANY3P) with real-device logs (implementation complete)
- [ ] Validate real-time zone guidance on K3-series devices
- [x] Configurable poll windows with native time picker
- [x] Manual polling mode with `oclean_ble.poll` action
- [ ] Publish to HACS default repository
- [ ] Decode remaining unknown fields in session data

---

## Requirements

- Home Assistant **2023.4** or newer
- HA **Bluetooth** integration enabled (built-in; requires a compatible Bluetooth adapter or ESPHome proxy)
- `bleak` and `bleak-retry-connector` are bundled with HA's bluetooth stack – no separate installation required

---

## For Developers

Full protocol documentation including GATT UUIDs, command tables, byte layouts, and device type matrix:
→ [BLE Protocol Reference](docs/BLE-PROTOCOL-REFERENCE.md)

---

## Contributing & Feedback

Feedback and contributions are welcome.

- **Bug reports / feature requests:** Open an issue on GitHub
- **New device data:** Enable debug logging, brush your teeth, copy the raw hex output from the HA log, and open an issue
- **Pull requests:** PRs are welcome – please include a brief description of what was tested

---

## License

MIT – see [LICENSE](LICENSE)

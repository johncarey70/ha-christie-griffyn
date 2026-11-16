"""Config flow, entities, commands and service against the fake projector."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.christie_griffyn.const import CONF_SCAN_INTERVAL, DOMAIN, EVENT_MESSAGE
from custom_components.christie_griffyn.diagnostics import async_get_config_entry_diagnostics
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .fake_projector import FakeProjector
from .recorded import MAC, SERIAL

ENTRY_MAC = MAC.lower()


async def setup_entry(hass: HomeAssistant, projector: FakeProjector) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Griffyn",
        unique_id=ENTRY_MAC,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: projector.port},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def poll(hass: HomeAssistant, seconds: int) -> None:
    """Move time forward and wait for the scheduled poll (a background task)."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done(wait_background_tasks=True)


def enable(hass: HomeAssistant, entity_id: str) -> None:
    er.async_get(hass).async_update_entity(entity_id, disabled_by=None)


async def test_flow_creates_entry_with_queries_only(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: " 127.0.0.1 ", CONF_PORT: projector.port, CONF_NAME: "Theater Projector"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Theater Projector"
    assert result["data"] == {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port}
    assert result["result"].unique_id == ENTRY_MAC
    assert projector.received and all("?" in message for message in projector.received)
    await hass.async_block_till_done()


async def test_flow_cannot_connect(hass: HomeAssistant, socket_enabled: None) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_NAME: "Griffyn"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_not_christie(hass: HomeAssistant, projector: FakeProjector) -> None:
    projector.silent.add("PWR?")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port, CONF_NAME: "x"}
    )
    assert result["errors"] == {"base": "not_christie"}


async def test_flow_falls_back_to_serial_and_detects_duplicates(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    del projector.replies["NET+MAC0?"]
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_HOST: "10.0.0.9"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port, CONF_NAME: "x"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_entities(hass: HomeAssistant, projector: FakeProjector) -> None:
    entry = await setup_entry(hass, projector)
    assert entry.state is ConfigEntryState.LOADED
    # Setting up only reads.
    assert projector.sets == []

    state = hass.states.get("switch.griffyn_power")
    assert state.state == "on"
    assert state.attributes["power_state"] == "on"
    assert hass.states.get("sensor.griffyn_power_state").state == "on"
    assert hass.states.get("switch.griffyn_shutter_open").state == "on"
    assert hass.states.get("sensor.griffyn_laser_hours").state == "1714.2"
    assert hass.states.get("sensor.griffyn_laser_on_cycles").state == "523"
    assert hass.states.get("sensor.griffyn_projector_hours").state == "1728.9"
    assert hass.states.get("sensor.griffyn_resolution").state == "4096x2160"
    assert hass.states.get("sensor.griffyn_frame_rate").state == "23.98"
    assert hass.states.get("sensor.griffyn_dynamic_range").state == "SDR"
    assert hass.states.get("sensor.griffyn_bit_depth").state == "8"
    assert hass.states.get("sensor.griffyn_color_format").state == "RGB-limited 4:4:4"
    assert hass.states.get("binary_sensor.griffyn_signal_present").state == "on"
    assert hass.states.get("binary_sensor.griffyn_problem").state == "off"
    assert hass.states.get("sensor.griffyn_status").state == "ok"
    assert hass.states.get("number.griffyn_laser_power").state == "30.0"
    assert hass.states.get("sensor.griffyn_air_intake_temperature").state == "25.0"
    assert hass.states.get("sensor.griffyn_light_source_state").state == "On"

    select = hass.states.get("select.griffyn_input")
    assert select.state == "One-Port HDMI0"
    assert "One-Port [HDBaseT]" in select.attributes["options"]
    assert "Two-Port DP (621)" in select.attributes["options"]

    profile = hass.states.get("select.griffyn_profile")
    assert profile.state == "unknown"
    assert profile.attributes["options"][0] == "0: Defaults"
    assert "5: GRIFFYN 4K35-RGB_2025-12-11 60" in profile.attributes["options"]
    assert not [o for o in profile.attributes["options"] if "Empty" in o]

    assert hass.states.get("select.griffyn_test_pattern").state == "Off"
    assert "FLIR" not in hass.states.get("select.griffyn_test_pattern").attributes["options"]
    assert hass.states.get("select.griffyn_fan_profile").state == "Standard"
    assert hass.states.get("select.griffyn_gamma_function").state == "Auto Detect"

    reg = er.async_get(hass)
    assert reg.async_get("number.griffyn_lens_zoom").disabled_by is not None
    assert reg.async_get("sensor.griffyn_formatter_blue_temperature").disabled_by is not None
    device_entries = er.async_entries_for_config_entry(reg, entry.entry_id)
    assert len(device_entries) > 80


async def test_lens_range_from_calibration(hass: HomeAssistant, projector: FakeProjector) -> None:
    entry = await setup_entry(hass, projector)
    enable(hass, "number.griffyn_lens_zoom")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("number.griffyn_lens_zoom")
    assert state.state == "15"
    assert state.attributes["min"] == -1093
    assert state.attributes["max"] == 1102


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data", "sent"),
    [
        ("number", "set_value", "number.griffyn_laser_power", {"value": 45.5}, "$LAS+POWR 455"),
        (
            "select",
            "select_option",
            "select.griffyn_input",
            {"option": "One-Port HDMI1"},
            "$CHA 601",
        ),
        (
            "select",
            "select_option",
            "select.griffyn_fan_profile",
            {"option": "Quiet"},
            "$TMC+MODE 1",
        ),
        ("switch", "turn_off", "switch.griffyn_shutter_open", {}, "$SHU 1"),
        ("switch", "turn_on", "switch.griffyn_freeze_image", {}, "$FRZ 1"),
        ("number", "set_value", "number.griffyn_gamma", {"value": 2.4}, "$GAM 2400"),
    ],
)
async def test_commands(
    hass: HomeAssistant,
    projector: FakeProjector,
    domain: str,
    service: str,
    entity_id: str,
    data: dict,
    sent: str,
) -> None:
    await setup_entry(hass, projector)
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    assert projector.sets == [sent]


async def test_set_value_is_read_back(hass: HomeAssistant, projector: FakeProjector) -> None:
    await setup_entry(hass, projector)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.griffyn_laser_power", "value": 50},
        blocking=True,
    )
    assert hass.states.get("number.griffyn_laser_power").state == "50.0"


async def test_laser_power_range(hass: HomeAssistant, projector: FakeProjector) -> None:
    from homeassistant.exceptions import ServiceValidationError

    await setup_entry(hass, projector)
    state = hass.states.get("number.griffyn_laser_power")
    assert state.attributes["min"] == 30
    assert state.attributes["max"] == 100
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.griffyn_laser_power", "value": 29.9},
            blocking=True,
        )
    assert projector.sets == []
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.griffyn_laser_power", "value": 30},
        blocking=True,
    )
    assert projector.sets == ["$LAS+POWR 300"]
    assert hass.states.get("number.griffyn_laser_power").state == "30.0"


async def test_power_off_and_on(hass: HomeAssistant, projector: FakeProjector) -> None:
    await setup_entry(hass, projector)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.griffyn_power"}, blocking=True
    )
    await hass.async_block_till_done()
    assert projector.sets == ["PWR 0"]
    assert hass.states.get("sensor.griffyn_power_state").state == "cooling_down"
    assert hass.states.get("switch.griffyn_power").state == "off"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.griffyn_power"}, blocking=True
    )
    await hass.async_block_till_done()
    assert projector.sets == ["PWR 0", "PWR 1"]
    assert hass.states.get("sensor.griffyn_power_state").state == "warming_up"
    assert hass.states.get("switch.griffyn_power").state == "on"


async def test_power_change_waits_before_refresh(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    entry = await setup_entry(hass, projector)
    assert hass.states.get("number.griffyn_laser_power").state == "30.0"
    assert hass.states.get("switch.griffyn_shutter_open").state == "on"

    slept = asyncio.Event()
    release = asyncio.Event()
    delays: list[float] = []

    async def gated_sleep(delay: float) -> None:
        delays.append(delay)
        slept.set()
        await release.wait()

    with (
        patch("custom_components.christie_griffyn.switch.POST_POWER_REFRESH_DELAY", 20),
        patch("custom_components.christie_griffyn.switch.asyncio.sleep", side_effect=gated_sleep),
    ):
        task = hass.async_create_task(
            hass.services.async_call(
                "switch", "turn_off", {"entity_id": "switch.griffyn_power"}, blocking=True
            )
        )
        await slept.wait()
        assert delays == [20]
        assert projector.sets == ["PWR 0"]
        # The follow-up refresh has not run yet; last state stays on.
        assert hass.states.get("switch.griffyn_power").state == "on"
        assert hass.states.get("number.griffyn_laser_power").state == "30.0"

        # A poll during the wait must not mark entities unavailable, even if
        # the projector is not answering.
        projector.silent.add("PWR?")
        await entry.runtime_data.coordinator.async_refresh()
        assert hass.states.get("switch.griffyn_power").state == "on"
        assert hass.states.get("number.griffyn_laser_power").state == "30.0"
        assert hass.states.get("switch.griffyn_shutter_open").state == "on"
        projector.silent.clear()

        release.set()
        await task

    assert hass.states.get("sensor.griffyn_power_state").state == "cooling_down"
    assert hass.states.get("switch.griffyn_power").state == "off"
    assert hass.states.get("number.griffyn_laser_power").state == "30.0"


async def test_profile_select_is_assumed(hass: HomeAssistant, projector: FakeProjector) -> None:
    await setup_entry(hass, projector)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.griffyn_profile", "option": "3: GRIFFYN 4K35-RGB_2025-12-11 30"},
        blocking=True,
    )
    state = hass.states.get("select.griffyn_profile")
    assert projector.sets == ["$PRO 3"]
    assert state.state == "3: GRIFFYN 4K35-RGB_2025-12-11 30"
    assert state.attributes["assumed_state"] is True
    assert state.attributes["profile_number"] == 3


async def test_rejected_command_raises(hass: HomeAssistant, projector: FakeProjector) -> None:
    from homeassistant.exceptions import HomeAssistantError

    await setup_entry(hass, projector)
    projector.nak.add("FRZ")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": "switch.griffyn_freeze_image"}, blocking=True
        )


async def test_standby_disables_video_controls(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    projector.set_power(0)
    projector.rejected.update({"CHA?", "SIN?", "ITP?", "FRZ?", "DTL?", "CSP?"})
    projector.replies["SST+SIGN?"] = '(SST+SIGN!050 000 "N/A" "Output Frequency")'
    await setup_entry(hass, projector)
    assert hass.states.get("switch.griffyn_power").state == "off"
    assert hass.states.get("sensor.griffyn_power_state").state == "standby"
    assert hass.states.get("select.griffyn_input").state == STATE_UNAVAILABLE
    assert hass.states.get("switch.griffyn_freeze_image").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.griffyn_signal_present").state == "off"
    assert hass.states.get("sensor.griffyn_resolution").state == "unknown"
    # Settings that still answer in standby stay available.
    assert hass.states.get("number.griffyn_laser_power").state == "30.0"


async def test_unreachable_projector_retries_setup(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    projector.silent.add("PWR?")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ENTRY_MAC, data={CONF_HOST: "127.0.0.1", CONF_PORT: projector.port}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_goes_unavailable_and_recovers(hass: HomeAssistant, projector: FakeProjector) -> None:
    await setup_entry(hass, projector)
    projector.silent.add("PWR?")
    await poll(hass, 31)
    assert hass.states.get("switch.griffyn_power").state == STATE_UNAVAILABLE
    projector.silent.clear()
    await poll(hass, 62)
    assert hass.states.get("switch.griffyn_power").state == "on"


async def test_timeout_mid_poll_keeps_old_values(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    await setup_entry(hass, projector)
    projector.silent.add("SHU?")
    await poll(hass, 31)
    assert hass.states.get("switch.griffyn_power").state == "on"
    assert hass.states.get("switch.griffyn_shutter_open").state == "on"
    assert hass.states.get("number.griffyn_laser_power").state == "30.0"


async def test_send_command_service(hass: HomeAssistant, projector: FakeProjector) -> None:
    await setup_entry(hass, projector)
    response = await hass.services.async_call(
        DOMAIN, "send_command", {"command": "LAS+POWR?"}, blocking=True, return_response=True
    )
    assert response == {"command": "(LAS+POWR?)", "replies": ["(LAS+POWR!300)"]}
    response = await hass.services.async_call(
        DOMAIN, "send_command", {"command": "(OSD 0)"}, blocking=True, return_response=True
    )
    assert response["replies"] == ["$"]
    assert "$OSD 0" in projector.sets

    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            {"command": "hello world"},
            blocking=True,
            return_response=True,
        )


async def test_async_message_fires_event(hass: HomeAssistant, projector: FakeProjector) -> None:
    await setup_entry(hass, projector)
    events = []
    hass.bus.async_listen(EVENT_MESSAGE, events.append)
    projector.unsolicited.append(
        '(65535 00000 ERR00000 "System Warning: \\(SST+TEMP?002\\) Air Intake = 40 °C")'
    )
    await poll(hass, 31)
    assert len(events) == 1
    assert events[0].data["kind"] == "ERR"
    assert events[0].data["text"].startswith("System Warning: (SST+TEMP?002)")
    assert hass.states.get("sensor.griffyn_last_message").state.startswith("System Warning")


async def test_warning_status_sets_problem(hass: HomeAssistant, projector: FakeProjector) -> None:
    projector.replies["SST+COOL?"] = projector.replies["SST+COOL?"].replace(
        '(SST+COOL!047 000 "2300 RPM"', '(SST+COOL!047 001 "300 RPM"'
    )
    await setup_entry(hass, projector)
    assert hass.states.get("binary_sensor.griffyn_problem").state == "on"
    status = hass.states.get("sensor.griffyn_status")
    assert status.state == "warning"
    assert status.attributes["problems"] == ["Power Supply 1 Fan: 300 RPM"]


async def test_options_flow(hass: HomeAssistant, projector: FakeProjector) -> None:
    entry = await setup_entry(hass, projector)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_SCAN_INTERVAL: 60}
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=60)


async def test_diagnostics_redacts(hass: HomeAssistant, projector: FakeProjector) -> None:
    entry = await setup_entry(hass, projector)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = repr(diag)
    assert "127.0.0.1" not in text
    assert ENTRY_MAC not in text
    assert diag["status"]["CONF_001"]["value"] == "**REDACTED**"
    assert diag["firmware"] == "1.3.7"


async def test_unload_closes_connection(hass: HomeAssistant, projector: FakeProjector) -> None:
    entry = await setup_entry(hass, projector)
    client = entry.runtime_data.client
    assert client.connected
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not client.connected

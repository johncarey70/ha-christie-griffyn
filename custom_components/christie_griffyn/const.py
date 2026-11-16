"""Constants for the Christie Griffyn integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "christie_griffyn"
MANUFACTURER: Final = "Christie"

DEFAULT_NAME: Final = "Griffyn"
DEFAULT_PORT: Final = 3002

CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600

# Network timing. The projector may answer slowly while warming up, so
# individual queries get a short timeout and a poll stops early when one
# times out instead of waiting on every remaining query.
CONNECT_TIMEOUT: Final = 5.0
QUERY_TIMEOUT: Final = 4.0
LIST_TIMEOUT: Final = 8.0
ACK_TIMEOUT: Final = 10.0
# Wait for an error after a command sent without acknowledgement.
NO_ACK_SETTLE: Final = 0.5
# Give the projector a moment after a command before reading back.
POST_COMMAND_DELAY: Final = 1.0
# After power on/off, wait before the follow-up refresh so entities
# don't go unavailable while the projector is warming or cooling.
POST_POWER_REFRESH_DELAY: Final = 20.0

# Status groups and settings are read on every Nth poll; power, shutter,
# input and signal on every poll. Lists and device info are read at start,
# when power changes and every STATIC_EVERY polls.
SLOW_EVERY: Final = 4
STATIC_EVERY: Final = 120

EVENT_MESSAGE: Final = f"{DOMAIN}_message"

SERVICE_SEND_COMMAND: Final = "send_command"
ATTR_COMMAND: Final = "command"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_TIMEOUT: Final = "timeout"

# Power states from (PWR?).
POWER_STANDBY: Final = 0
POWER_ON: Final = 1
POWER_COOLING: Final = 10
POWER_WARMING: Final = 11
POWER_STATE_KEYS: Final[dict[int, str]] = {
    POWER_STANDBY: "standby",
    POWER_ON: "on",
    POWER_COOLING: "cooling_down",
    POWER_WARMING: "warming_up",
}

# Queries read on every poll (besides PWR?).
FAST_QUERIES: Final[tuple[str, ...]] = (
    "SHU",
    "CHA",
    "SIN",
    "LAS+POWR",
    "ITP",
    "FRZ",
    "FRD+TIME",
)

# Single-value settings read every SLOW_EVERY polls.
SLOW_QUERIES: Final[tuple[str, ...]] = (
    "APW",
    "PWR+ELEC",
    "SIN+PORT",
    "LAS+MODE",
    "LAS+CFCM",
    "LAS+REDP",
    "LAS+GRNP",
    "LAS+BLUP",
    "LAS+WHTX",
    "LAS+WHTY",
    "TMC+MODE",
    "STH+MODE",
    "OSD",
    "MSP",
    "ETP",
    "DTL",
    "CSP",
    "BGC",
    "GAM",
    "GAM+MAXL",
    "GAM+MINL",
    "GAM+PQWL",
    "FRD",
    "SZP",
    "SOR",
    "TDM",
    "TDN",
    "TDO",
    "RBK+SLCT",
    "RBK+TIME",
    "RBK+LOSL",
    "ENH+SLCT",
    "EDO",
    "FMD",
    "KEN+FRNT",
    "KEN+REAR",
    "KEN+WIRE",
    "LOC+LANG",
    "LOC+TEMP",
    "WRP+SLCT",
    "WRP+KGAN",
    "EBL+SLCT",
    "EBB+SLCT",
    "SPS+COLR",
    "THM",
    "CLE",
    "CHL+INPT",
    "SDI",
    "BLO+SLCT",
    "LCB+LOCK",
    "LHO",
    "LVO",
    "ZOM",
    "FCS",
)

# Status system groups read every SLOW_EVERY polls, and the signal group
# on every poll.
SIGNAL_GROUP: Final = "SIGN"
STATUS_GROUPS: Final[tuple[str, ...]] = ("SYST", "TEMP", "COOL", "LGHT")
STATIC_GROUPS: Final[tuple[str, ...]] = ("CONF", "VERS")

# Lists of choices (?L) read with the static data.
LIST_QUERIES: Final[tuple[str, ...]] = ("CHA", "SIN", "PRO", "ITP", "WRP+SLCT")
# Lens axis ranges (?m).
RANGE_QUERIES: Final[tuple[str, ...]] = ("LHO", "LVO", "ZOM", "FCS")


def scan_interval_from_seconds(seconds: int) -> timedelta:
    """Return a polling interval, never faster than the minimum."""
    return timedelta(seconds=max(MIN_SCAN_INTERVAL, seconds))

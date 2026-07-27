"""Identify the machine a card key is bound to.

The identifier has to survive everyday hardware changes. It used to mix in the
computer name, the user domain, the hostname and a network adapter address, so
plugging in a docking station or installing a VPN adapter changed it - the user
lost the activation, and with one-device cards could not activate again.

Windows machines now use MachineGuid alone: it only changes when the OS is
reinstalled, which is exactly when re-activating is reasonable. The old value is
still computed so existing activations keep working; see
core/feishu_license_client.py for how the old value is swapped for the new one.
"""

from __future__ import annotations

import hashlib
import os
import platform
import uuid


# Never change this: it would invalidate every activation already in the wild.
MACHINE_ID_SALT = "BBDown3.0"


def get_machine_id() -> str:
    """The identifier this build binds a card key to."""
    guid = _read_windows_machine_guid()
    if guid:
        return _hash_parts([guid])
    return get_legacy_machine_id()


def get_legacy_machine_id() -> str:
    """The identifier used up to 4.0. Kept so existing users are not locked out."""
    return _hash_parts(_legacy_parts())


def machine_id_candidates() -> list[str]:
    """Every identifier this machine may already be registered under, newest first."""
    current = get_machine_id()
    legacy = get_legacy_machine_id()
    return [current] if legacy == current else [current, legacy]


def _hash_parts(parts: list[str]) -> str:
    raw = "|".join(part for part in parts if part) or "unknown-machine"
    return hashlib.sha256(f"{MACHINE_ID_SALT}|{raw}".encode("utf-8")).hexdigest()[:32]


def _legacy_parts() -> list[str]:
    parts: list[str] = []
    guid = _read_windows_machine_guid()
    if guid:
        parts.append(guid)
    parts.extend(
        [
            os.environ.get("COMPUTERNAME", ""),
            os.environ.get("USERDOMAIN", ""),
            platform.node(),
            str(uuid.getnode()),
        ]
    )
    return [part.strip() for part in parts if part and part.strip()]


def _read_windows_machine_guid() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except Exception:
        return ""

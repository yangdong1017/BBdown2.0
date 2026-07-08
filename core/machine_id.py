from __future__ import annotations

import hashlib
import os
import platform
import uuid


MACHINE_ID_SALT = "BBDown3.0"


def get_machine_id() -> str:
    raw = "|".join(part for part in _machine_parts() if part)
    if not raw:
        raw = "unknown-machine"
    return hashlib.sha256(f"{MACHINE_ID_SALT}|{raw}".encode("utf-8")).hexdigest()[:32]


def _machine_parts() -> list[str]:
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
            return str(value)
    except Exception:
        return ""

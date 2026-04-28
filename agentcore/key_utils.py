from __future__ import annotations

import raylib as rl


def find_key_for_char(char: str) -> int:
    """Return the Raylib key code that produces *char* in the current keyboard layout.

    Uses glfwGetKeyName (layout-aware) so Dvorak, Colemak, etc. work correctly.
    Falls back to the QWERTY key code if no match is found.
    """
    target = char.lower()
    fallback = getattr(rl, f"KEY_{char.upper()}", rl.KEY_NULL)
    for key in range(32, 350):
        raw = rl.glfwGetKeyName(key, 0)
        if raw != rl.ffi.NULL:
            name = rl.ffi.string(raw).decode(errors="ignore").lower()
            if name == target:
                return key
    return fallback

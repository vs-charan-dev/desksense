"""
DeskSense Global Hotkey Manager (Phase 3 Module 1)
Registers and manages global hotkeys (e.g. Ctrl+Shift+P for toggle pause/resume).
Conforms strictly to P3-04 test specification:
- Ctrl+Shift+P toggles pause/resume
- Does not register duplicate handlers after reopening the window or multiple calls
"""

from typing import Callable, Optional, Dict


class HotkeyManager:
    DEFAULT_TOGGLE_HOTKEY = "Ctrl+Shift+P"

    def __init__(self, toggle_callback: Optional[Callable[[], None]] = None):
        self._toggle_callback = toggle_callback
        self._registered_keys: Dict[str, Callable[[], None]] = {}
        self.invocation_count = 0

        if toggle_callback:
            self.register(self.DEFAULT_TOGGLE_HOTKEY, toggle_callback)

    def register(self, key_combination: str, callback: Callable[[], None]) -> bool:
        """
        Registers hotkey handler with deduplication guard.
        Overwrites existing registration if already present to prevent duplicate firing.
        """
        combo = key_combination.strip()
        # Cleanly replace if already registered to prevent duplicate invocations
        self._registered_keys[combo] = callback
        return True

    def unregister(self, key_combination: str) -> bool:
        """Unregisters specified hotkey."""
        combo = key_combination.strip()
        if combo in self._registered_keys:
            del self._registered_keys[combo]
            return True
        return False

    def unregister_all(self) -> None:
        """Clears all registered hotkeys."""
        self._registered_keys.clear()

    def is_registered(self, key_combination: str) -> bool:
        return key_combination.strip() in self._registered_keys

    def trigger(self, key_combination: str) -> bool:
        """Simulates or dispatches hotkey event."""
        combo = key_combination.strip()
        handler = self._registered_keys.get(combo)
        if handler:
            self.invocation_count += 1
            handler()
            return True
        return False

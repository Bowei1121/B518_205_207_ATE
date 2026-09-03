"""Small, permission-free macOS global-hotkey adapter.

The implementation registers exactly one key combination with Carbon.  It does
not install a keyboard event monitor, so it does not read unrelated keystrokes
or require Accessibility/Input Monitoring permission.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Callable, Optional, Protocol


COMMAND_SHIFT_M_KEYCODE = 46  # kVK_ANSI_M
COMMAND_SHIFT_MODIFIERS = 0x0100 | 0x0200  # cmdKey | shiftKey


class HotkeyRegistration(Protocol):
    available: bool
    message: str

    def close(self) -> None:
        ...


@dataclass
class UnavailableHotkey:
    message: str
    available: bool = False

    def close(self) -> None:
        pass


class GlobalHotkeyError(RuntimeError):
    pass


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class CarbonGlobalHotkey:
    """Register Command+Shift+M through the Carbon Event Manager."""

    available = True
    message = "可用：Command+Shift+M（全域）"

    _KEYBOARD_EVENT_CLASS = 0x6B657962  # 'keyb'
    _HOTKEY_PRESSED = 6  # kEventHotKeyPressed
    _SIGNATURE = 0x42353138  # 'B518'

    def __init__(self, callback: Callable[[], None], carbon: object | None = None):
        self._callback = callback
        self._carbon = carbon or ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        self._handler_ref = ctypes.c_void_p()
        self._hotkey_ref = ctypes.c_void_p()
        self._handler = None
        self._configure_signatures()
        self._install()

    def _configure_signatures(self) -> None:
        self._carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        self._carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.InstallEventHandler.restype = ctypes.c_int32
        self._carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, _EventHotKeyID, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.RegisterEventHotKey.restype = ctypes.c_int32
        self._carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        self._carbon.UnregisterEventHotKey.restype = ctypes.c_int32
        self._carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]
        self._carbon.RemoveEventHandler.restype = ctypes.c_int32

    def _install(self) -> None:
        handler_type = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

        def on_event(_next_handler: object, _event: object, _user_data: object) -> int:
            self._callback()
            return 0

        self._handler = handler_type(on_event)
        event_type = _EventTypeSpec(self._KEYBOARD_EVENT_CLASS, self._HOTKEY_PRESSED)
        target = self._carbon.GetApplicationEventTarget()
        status = self._carbon.InstallEventHandler(
            target, ctypes.cast(self._handler, ctypes.c_void_p), 1, ctypes.byref(event_type), None,
            ctypes.byref(self._handler_ref),
        )
        if status != 0:
            raise GlobalHotkeyError("無法安裝快捷鍵處理器（Carbon {}）".format(status))
        hotkey_id = _EventHotKeyID(self._SIGNATURE, 1)
        status = self._carbon.RegisterEventHotKey(
            COMMAND_SHIFT_M_KEYCODE, COMMAND_SHIFT_MODIFIERS, hotkey_id, target, 0,
            ctypes.byref(self._hotkey_ref),
        )
        if status != 0:
            self.close()
            raise GlobalHotkeyError("Command+Shift+M 無法註冊（可能已被其他程式使用，Carbon {}）".format(status))

    def close(self) -> None:
        if self._hotkey_ref and self._hotkey_ref.value:
            self._carbon.UnregisterEventHotKey(self._hotkey_ref)
            self._hotkey_ref = ctypes.c_void_p()
        if self._handler_ref and self._handler_ref.value:
            self._carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()
        self._handler = None


def create_global_hotkey(
    callback: Callable[[], None],
    platform_name: Optional[str] = None,
    implementation: Callable[[Callable[[], None]], HotkeyRegistration] = CarbonGlobalHotkey,
) -> HotkeyRegistration:
    """Create the global hotkey or return an explanatory non-global fallback."""
    if (platform_name or sys.platform) != "darwin":
        return UnavailableHotkey("目前系統不是 macOS；僅可在本程式有焦點時使用快捷鍵。")
    try:
        return implementation(callback)
    except (OSError, GlobalHotkeyError) as error:
        return UnavailableHotkey(str(error))

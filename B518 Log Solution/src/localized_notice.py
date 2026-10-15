"""Acknowledgement-only App notices with live language refresh."""
import tkinter as tk
from tkinter import ttk


class LanguageRefreshNotifications:
    """Dispatch the existing Tk language notification to live App receivers."""

    def __init__(self, root, on_result):
        self.root = root
        self.on_result = on_result
        self.receivers = {}
        self.failures = {}
        self.next_token = 0
        self.binding = root.bind("<<AppLanguageChanged>>", self._changed, add="+")

    def register(self, name, refresh, alive):
        self.next_token += 1
        token = self.next_token
        self.receivers[token] = (name, refresh, alive)

        def unregister():
            self.receivers.pop(token, None)
            if self.failures.pop(token, None) is not None:
                self.on_result(self.failures, {})

        return unregister

    def notify(self):
        self.root.event_generate("<<AppLanguageChanged>>")

    def retry(self):
        self._refresh(tuple(self.failures))

    def close(self):
        self.receivers.clear()
        self.failures.clear()
        root = self.root
        binding = self.binding
        self.root = None
        self.binding = None
        self.on_result = None
        try:
            if root is not None and binding is not None:
                root.unbind("<<AppLanguageChanged>>", binding)
        except (AttributeError, tk.TclError):
            pass

    def _changed(self, _event=None):
        self._refresh(tuple(self.receivers))

    def _refresh(self, tokens):
        newly_failed = {}
        for token in tokens:
            receiver = self.receivers.get(token)
            if receiver is None:
                self.failures.pop(token, None)
                continue
            name, refresh, alive = receiver
            try:
                if not alive():
                    self.receivers.pop(token, None)
                    self.failures.pop(token, None)
                    continue
                refresh()
            except Exception as error:
                self.failures[token] = (name, str(error))
                newly_failed[token] = (name, str(error))
            else:
                self.failures.pop(token, None)
        try:
            self.on_result(self.failures, newly_failed)
        except Exception:
            # Reporting is downstream of dispatch and cannot stop receivers.
            return


def show_notice(title, message, *, parent, text_provider, register_refresh,
                receiver_name=None, background="#f3f4f6", foreground="#111827"):
    """Keep the modal acknowledgement effect while Tk continues processing events."""
    previous_focus = parent.focus_get()
    previous_grab = parent.grab_current()
    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent)
    window.geometry("640x400")
    window.minsize(480, 320)
    window.grid_columnconfigure(0, weight=1)
    window.grid_rowconfigure(0, weight=1)
    frame = ttk.Frame(window, padding=16)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(0, weight=1)
    body = tk.Text(
        frame, wrap="word", height=8, background=background, foreground=foreground,
        relief="solid", borderwidth=1, highlightthickness=0,
        selectbackground="#dbeafe", selectforeground=foreground)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=body.yview)
    body.configure(yscrollcommand=scrollbar.set)
    body.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    body.insert("1.0", message)
    body.configure(state="disabled")
    acknowledge = ttk.Button(window, command=window.destroy)
    acknowledge.grid(row=1, column=0, sticky="e", padx=16, pady=(0, 16))

    def refresh(_event=None):
        if not window.winfo_exists():
            return
        title_text, message_text, button_text = text_provider()
        top = body.yview()[0]
        window.title(title_text)
        body.configure(state="normal")
        body.delete("1.0", "end")
        body.insert("1.0", message_text)
        body.configure(state="disabled")
        body.yview_moveto(top)
        acknowledge.configure(text=button_text)

    unregister = register_refresh(receiver_name or title, refresh, window.winfo_exists)

    def restore_modal_focus(event=None):
        if event is not None and event.widget is not window:
            return
        try:
            if not window.winfo_exists() or not window.winfo_viewable():
                return
            if parent.grab_current() is not window:
                window.grab_set()
            acknowledge.focus_force()
        except tk.TclError:
            return

    window.protocol("WM_DELETE_WINDOW", window.destroy)
    window.bind("<Map>", restore_modal_focus, add="+")
    window.bind("<Return>", lambda _event: acknowledge.invoke())
    window.bind("<Escape>", lambda _event: window.destroy())
    try:
        refresh()
        try:
            window.wait_visibility()
        except tk.TclError:
            # Acknowledgement or WM close may arrive while macOS maps the notice.
            if window.winfo_exists():
                raise
            return
        window.grab_set()
        acknowledge.focus_set()
        parent.wait_window(window)
    finally:
        unregister()
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        if previous_focus is not None and previous_focus.winfo_exists():
            previous_focus.focus_set()

"""Acknowledgement-only App notices with live language refresh."""
import tkinter as tk
from tkinter import ttk


def show_notice(title, message, *, parent, text_provider):
    """Keep the modal acknowledgement effect while Tk continues processing events."""
    previous_focus = parent.focus_get()
    previous_grab = parent.grab_current()
    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent)
    window.geometry("560x280")
    window.minsize(360, 220)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    body = tk.Text(frame, wrap="word", height=8)
    scrollbar = ttk.Scrollbar(frame, command=body.yview)
    body.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    body.pack(fill="both", expand=True)
    body.insert("1.0", message)
    body.configure(state="disabled")
    acknowledge = ttk.Button(window, command=window.destroy)
    acknowledge.pack(pady=(0, 12))

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

    binding = parent.bind("<<AppLanguageChanged>>", refresh, add="+")
    window.protocol("WM_DELETE_WINDOW", window.destroy)
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
        parent.unbind("<<AppLanguageChanged>>", binding)
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        if previous_focus is not None and previous_focus.winfo_exists():
            previous_focus.focus_set()

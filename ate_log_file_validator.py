from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class ATELogValidatorApp:
    """Minimal macOS ATE log-file access validation tool."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ATE Log File Validator")
        self.root.geometry("900x650")
        self.root.minsize(700, 500)

        self.file_path_var = tk.StringVar()
        self.status_var = tk.StringVar(value="尚未選擇檔案")

        self._configure_appearance()
        self._build_ui()

    def _configure_appearance(self) -> None:
        """Use explicit colors so packaged apps stay readable in dark mode."""
        style = ttk.Style(self.root)

        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.root.configure(background="#f3f4f6")

        style.configure(
            ".",
            background="#f3f4f6",
            foreground="#111827",
            fieldbackground="#ffffff",
        )
        style.configure(
            "TButton",
            background="#e5e7eb",
            foreground="#111827",
            padding=(10, 6),
            borderwidth=1,
        )
        style.map(
            "TButton",
            background=[
                ("active", "#d1d5db"),
                ("pressed", "#cbd5e1"),
                ("disabled", "#f3f4f6"),
            ],
            foreground=[
                ("disabled", "#9ca3af"),
            ],
        )
        style.configure(
            "TEntry",
            fieldbackground="#ffffff",
            foreground="#111827",
            insertcolor="#111827",
        )

    def _build_ui(self) -> None:
        """Build the main user interface."""
        main_frame = ttk.Frame(self.root, padding=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # ------------------------------------------------------
        # Section 1: File path selection
        # ------------------------------------------------------
        path_frame = ttk.LabelFrame(
            main_frame,
            text="Log File Path",
            padding=12
        )
        path_frame.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12)
        )

        path_frame.columnconfigure(0, weight=1)

        self.path_entry = ttk.Entry(
            path_frame,
            textvariable=self.file_path_var
        )
        self.path_entry.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8)
        )

        browse_button = ttk.Button(
            path_frame,
            text="選擇檔案",
            command=self.select_file
        )
        browse_button.grid(
            row=0,
            column=1
        )

        read_button = ttk.Button(
            path_frame,
            text="重新讀取",
            command=self.read_selected_file
        )
        read_button.grid(
            row=0,
            column=2,
            padx=(8, 0)
        )

        # ------------------------------------------------------
        # Status
        # ------------------------------------------------------
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 12)
        )

        ttk.Label(
            status_frame,
            text="Status:"
        ).pack(side=tk.LEFT)

        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_var
        )
        self.status_label.pack(
            side=tk.LEFT,
            padx=(8, 0)
        )

        # ------------------------------------------------------
        # Section 2: Log content display
        # ------------------------------------------------------
        content_frame = ttk.LabelFrame(
            main_frame,
            text="Log Content",
            padding=12
        )
        content_frame.grid(
            row=2,
            column=0,
            sticky="nsew"
        )

        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            content_frame,
            wrap=tk.NONE,
            font=("Menlo", 12),
            background="#ffffff",
            foreground="#111827",
            insertbackground="#111827",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
        )
        self.log_text.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        # Vertical scrollbar
        vertical_scrollbar = ttk.Scrollbar(
            content_frame,
            orient=tk.VERTICAL,
            command=self.log_text.yview
        )
        vertical_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        # Horizontal scrollbar
        horizontal_scrollbar = ttk.Scrollbar(
            content_frame,
            orient=tk.HORIZONTAL,
            command=self.log_text.xview
        )
        horizontal_scrollbar.grid(
            row=1,
            column=0,
            sticky="ew"
        )

        self.log_text.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set
        )

    def select_file(self) -> None:
        """Open a native file-selection dialog."""
        selected_file = filedialog.askopenfilename(
            title="選擇 ATE Log 檔案",
            filetypes=[
                ("Log files", "*.log"),
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ]
        )

        if not selected_file:
            return

        self.file_path_var.set(selected_file)
        self.read_selected_file()

    def read_selected_file(self) -> None:
        """Read the selected file and display its content."""
        raw_path = self.file_path_var.get().strip()

        if not raw_path:
            self.status_var.set("尚未指定檔案路徑")
            return

        file_path = Path(raw_path)

        if not file_path.exists():
            self.status_var.set("Read Failed：檔案不存在")
            messagebox.showerror(
                "File Error",
                f"找不到檔案：\n{file_path}"
            )
            return

        if not file_path.is_file():
            self.status_var.set("Read Failed：選擇的路徑不是檔案")
            messagebox.showerror(
                "File Error",
                f"選擇的路徑不是一般檔案：\n{file_path}"
            )
            return

        try:
            content, encoding = self._read_text_file(file_path)

            self.log_text.delete("1.0", tk.END)
            self.log_text.insert("1.0", content)

            file_size = file_path.stat().st_size

            self.status_var.set(
                f"Read Success | "
                f"Encoding: {encoding} | "
                f"Size: {file_size} bytes"
            )

        except PermissionError as exc:
            self.status_var.set(
                "Read Failed：Permission Denied"
            )

            messagebox.showerror(
                "Permission Error",
                "程式無法讀取此檔案。\n\n"
                f"Path:\n{file_path}\n\n"
                f"Error:\n{exc}"
            )

        except Exception as exc:
            self.status_var.set(
                f"Read Failed：{type(exc).__name__}"
            )

            messagebox.showerror(
                "Read Error",
                "檔案讀取失敗。\n\n"
                f"Path:\n{file_path}\n\n"
                f"Error Type:\n{type(exc).__name__}\n\n"
                f"Error:\n{exc}"
            )

    @staticmethod
    def _read_text_file(file_path: Path) -> tuple[str, str]:
        """
        Try common encodings.

        ATE logs may not always be UTF-8, especially older test systems.
        """
        encodings = [
            "utf-8",
            "utf-8-sig",
            "big5",
            "cp950",
            "latin-1",
        ]

        last_error: Exception | None = None

        for encoding in encodings:
            try:
                content = file_path.read_text(
                    encoding=encoding
                )
                return content, encoding

            except UnicodeDecodeError as exc:
                last_error = exc

        raise UnicodeError(
            f"無法使用支援的文字編碼讀取檔案。"
            f"Last error: {last_error}"
        )


def main() -> None:
    root = tk.Tk()
    ATELogValidatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

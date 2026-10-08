"""log フォルダのJSONから、starting.py の表示用ウィンドウを再現する。"""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


LOG_DIR = Path(__file__).resolve().parent / "log"


class LogChooser(tk.Tk):
    """./log/ 内のJSON一覧から、再現するファイルを選ぶ。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("表示ログの選択")
        self.resizable(False, False)
        self.files = sorted(LOG_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if LOG_DIR.is_dir() else []

        tk.Label(self, text="log フォルダのJSONファイル").pack(anchor="w", padx=12, pady=(12, 4))
        self.listbox = tk.Listbox(self, width=54, height=12)
        for path in self.files:
            self.listbox.insert("end", path.name)
        self.listbox.pack(padx=12, fill="both")
        if self.files:
            self.listbox.selection_set(0)
            self.listbox.activate(0)

        buttons = tk.Frame(self)
        buttons.pack(pady=12)
        tk.Button(buttons, text="OK", width=12, command=self.open_selected).pack(side="left", padx=4)
        tk.Button(buttons, text="キャンセル", width=12, command=self.destroy).pack(side="left", padx=4)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.open_selected())
        self.bind("<Return>", lambda _event: self.open_selected())
        self.bind("<Escape>", lambda _event: self.destroy())

    def open_selected(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showerror("選択エラー", "JSONファイルを選択してください。", parent=self)
            return
        path = self.files[selection[0]]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            messagebox.showerror("読み込みエラー", str(error), parent=self)
            return
        DisplayReplay(self, data)


class DisplayReplay(tk.Toplevel):
    """保存された表示内容を、starting.py の表示用ウィンドウと同じ並びに出す。"""

    def __init__(self, master: tk.Misc, data: dict) -> None:
        super().__init__(master)
        self.title("Go to the Start 表示")
        background = str(data.get("background") or "black")
        window = data.get("window") if isinstance(data.get("window"), dict) else {}
        width = max(640, int(window.get("width") or 640))
        height = max(360, int(window.get("height") or 360))
        self.configure(background=background)
        self.minsize(640, 360)
        self.geometry(f"{width}x{height}")

        content = tk.Frame(self, background=background)
        content.pack(expand=True)

        header = data.get("header") if isinstance(data.get("header"), dict) else {}
        header_label = self._label(content, background, header, foreground="orange")
        header_label.grid(row=0, column=0, pady=(0, 8))

        timer = data.get("timer") if isinstance(data.get("timer"), dict) else {}
        timer_label = self._label(content, background, timer, foreground="white")
        timer_label.configure(
            anchor=str(timer.get("anchor") or "center"),
            justify=str(timer.get("justify") or "center"),
        )
        if timer.get("compact"):
            timer_label.grid(row=1, column=0, sticky="w")
        else:
            timer_label.grid(row=1, column=0)

        lap = data.get("lap") if isinstance(data.get("lap"), dict) else {}
        if lap.get("visible"):
            lap_label = self._label(content, background, lap, foreground="white")
            lap_label.grid(row=2, column=0)

        table = tk.Frame(content, background=background, borderwidth=0, highlightthickness=0)
        table.grid(row=3, column=0, sticky="ew")
        row_index = 0
        for item in data.get("rows") or []:
            if isinstance(item, dict):
                self._table_row(table, background, row_index, item)
                row_index += 1
        result = data.get("result") if isinstance(data.get("result"), dict) else None
        if result:
            if data.get("result_rule"):
                rule = tk.Frame(table, height=2, background="white", borderwidth=0, highlightthickness=0)
                rule.grid(row=row_index, column=0, columnspan=3, sticky="ew", pady=(6, 4))
                row_index += 1
            self._table_row(table, background, row_index, result)

    def _label(self, parent: tk.Misc, background: str, spec: dict, foreground: str) -> tk.Label:
        return tk.Label(
            parent,
            text=str(spec.get("text") or ""),
            background=background,
            foreground=str(spec.get("foreground") or foreground),
            font=self._font(spec.get("font"), ("Yu Gothic UI", 24, "bold")),
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )

    def _table_row(self, table: tk.Frame, background: str, row: int, item: dict) -> None:
        name = tk.Label(
            table,
            text=str(item.get("name") or ""),
            background=background,
            foreground=str(item.get("foreground") or "white"),
            font=self._font(item.get("name_font"), ("Yu Gothic UI", 24, "bold")),
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            anchor="w",
        )
        value = tk.Label(
            table,
            text=str(item.get("value") or ""),
            background=background,
            foreground=str(item.get("value_foreground") or item.get("foreground") or "white"),
            font=self._font(item.get("value_font"), ("Yu Gothic UI", 24, "bold")),
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            anchor="e",
        )
        name.grid(row=row, column=0, sticky="w")
        value.grid(row=row, column=1, sticky="e", padx=(24, 0))
        fraction = str(item.get("fraction") or "")
        if fraction:
            fraction_label = tk.Label(
                table,
                text=fraction,
                background=background,
                foreground=str(item.get("value_foreground") or item.get("foreground") or "white"),
                font=self._font(item.get("value_font"), ("Yu Gothic UI", 24, "bold")),
                borderwidth=0,
                highlightthickness=0,
                padx=0,
                pady=0,
                anchor="w",
            )
            fraction_label.grid(row=row, column=2, sticky="w")

    @staticmethod
    def _font(spec: object, default: tuple[str, int, str]) -> tuple:
        if isinstance(spec, (list, tuple)) and len(spec) >= 2:
            family = str(spec[0])
            size = int(spec[1])
            weight = str(spec[2]) if len(spec) > 2 else "bold"
            return (family, max(1, size), weight)
        return default


def main() -> None:
    LogChooser().mainloop()


if __name__ == "__main__":
    main()

"""ETロボコン用プログラムを起動するランチャー。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox


BASE_DIR = Path(__file__).resolve().parent
BUTTON_FONT = ("Yu Gothic UI", 32, "bold")


class EtroboLauncher(tk.Tk):
    """各操作プログラムを別プロセスで起動する操作パネル。"""

    PROGRAMS = (
        ("キャリブレーション", "calibration.py"),
        ("競技", "starting.py"),
        ("表示", "displog.py"),
        ("結果", "result.py"),
    )

    def __init__(self) -> None:
        super().__init__()
        self.title("ETロボコン ランチャー")
        self.resizable(False, False)
        self._build_buttons()

    def _build_buttons(self) -> None:
        frame = tk.Frame(self, padx=24, pady=24)
        frame.grid(sticky="nsew")

        for row, (caption, filename) in enumerate(self.PROGRAMS):
            button = tk.Button(
                frame,
                text=caption,
                font=BUTTON_FONT,
                width=14,
                command=lambda target=filename: self.launch(target),
            )
            button.grid(row=row, column=0, sticky="ew", pady=8)

    def launch(self, filename: str) -> None:
        path = BASE_DIR / filename
        if not path.is_file():
            messagebox.showerror("起動エラー", f"{filename} が見つかりません。", parent=self)
            return

        try:
            subprocess.Popen([sys.executable, str(path)], cwd=BASE_DIR)
        except OSError as error:
            messagebox.showerror("起動エラー", str(error), parent=self)


def main() -> None:
    EtroboLauncher().mainloop()


if __name__ == "__main__":
    main()

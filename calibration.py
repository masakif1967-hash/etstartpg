"""ETロボコン用キャリブレーション（カウントダウン表示）プログラム。"""

from __future__ import annotations

import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional


class Calibration:
    """操作用・表示用の2画面でカウントダウンを制御する。"""

    DEFAULT_SECONDS = 120
    MIN_SECONDS = 0
    MAX_SECONDS = 120
    MIN_VOLUME = 0
    MAX_VOLUME = 100
    DEFAULT_TICK_VOLUME = 100
    DEFAULT_FINISHED_VOLUME = 100
    TICK_FREQUENCY_HZ = 1000
    TICK_DURATION_MS = 70
    FINISHED_FREQUENCY_HZ = 200
    FINISHED_DURATION_MS = 900
    NORMAL_FOREGROUND = "white"
    WARNING_FOREGROUND = "yellow"
    NORMAL_BACKGROUND = "black"
    FINISHED_BACKGROUND = "red"

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._running = False
        self._end_time: Optional[float] = None
        self._after_id: Optional[str] = None
        self._remaining_seconds = self.DEFAULT_SECONDS
        self._finished_announced = False
        self._paused = False

        self.root = root if root is not None else tk.Tk()
        self.root.title("キャリブレーション操作")
        self.root.resizable(False, False)
        self.root.option_add("*Font", "{Yu Gothic UI} 12")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_control_window()
        self._build_display_window()
        self._show_remaining(self._remaining_seconds)

    def _build_control_window(self) -> None:
        frame = tk.Frame(self.root, padx=16, pady=16)
        frame.grid(sticky="nsew")

        tk.Label(frame, text="カウントダウン時間（秒）").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        self.seconds_var = tk.StringVar(value=str(self.DEFAULT_SECONDS))
        self.seconds_entry = tk.Entry(frame, textvariable=self.seconds_var, width=10)
        self.seconds_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 12))

        tk.Label(frame, text="「ピッ」音量").grid(row=2, column=0, columnspan=4, sticky="w")
        self.tick_volume_var = tk.IntVar(value=self.DEFAULT_TICK_VOLUME)
        tk.Scale(
            frame, from_=self.MIN_VOLUME, to=self.MAX_VOLUME, orient="horizontal",
            variable=self.tick_volume_var,
        ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(0, 6))

        tk.Label(frame, text="終了ブザー音量").grid(row=4, column=0, columnspan=4, sticky="w")
        self.finished_volume_var = tk.IntVar(value=self.DEFAULT_FINISHED_VOLUME)
        tk.Scale(
            frame, from_=self.MIN_VOLUME, to=self.MAX_VOLUME, orient="horizontal",
            variable=self.finished_volume_var,
        ).grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, 10))

        self.start_button = tk.Button(frame, text="スタート", command=self.start)
        self.start_button.grid(row=6, column=0, padx=(0, 4))
        self.pause_button = tk.Button(frame, text="一時停止", command=self.pause)
        self.pause_button.grid(row=6, column=1, padx=4)
        tk.Button(frame, text="リセット", command=self.reset).grid(row=6, column=2, padx=4)
        tk.Button(frame, text="更新", command=self.update).grid(row=6, column=3, padx=(4, 0))

    def _build_display_window(self) -> None:
        self.display = tk.Toplevel(self.root)
        self.display.title("キャリブレーション表示")
        self.display.configure(background=self.NORMAL_BACKGROUND)
        self.display.minsize(320, 180)
        self.display.protocol("WM_DELETE_WINDOW", self.close)

        self.timer_label = tk.Label(
            self.display,
            background=self.NORMAL_BACKGROUND,
            foreground=self.NORMAL_FOREGROUND,
            font=("Arial", 64, "bold"),
        )
        self.timer_label.pack(expand=True, fill="both")
        self.display.bind("<Configure>", self._resize_font)

    @classmethod
    def parse_seconds(cls, value: str) -> int:
        """入力文字列を検証し、0～120の整数秒として返す。"""
        try:
            seconds = int(value.strip())
        except (AttributeError, ValueError):
            raise ValueError("カウントダウン時間は0～120の整数で入力してください。") from None

        if not cls.MIN_SECONDS <= seconds <= cls.MAX_SECONDS:
            raise ValueError("カウントダウン時間は0～120の範囲で入力してください。")
        return seconds

    @staticmethod
    def format_seconds(seconds: int) -> str:
        """秒数を表示用の MM:SS 形式に変換する。"""
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @classmethod
    def parse_volume(cls, value: int) -> int:
        """音量を0～100の整数へ正規化する。"""
        try:
            volume = int(value)
        except (TypeError, ValueError):
            raise ValueError("音量は0～100の整数で指定してください。") from None
        if not cls.MIN_VOLUME <= volume <= cls.MAX_VOLUME:
            raise ValueError("音量は0～100の範囲で指定してください。")
        return volume

    def start(self) -> None:
        """設定値からカウントダウンを開始する。"""
        if self._paused:
            self._resume()
            return

        seconds = self._get_input_seconds()
        if seconds is None:
            return

        self._cancel_scheduled_update()
        self._remaining_seconds = seconds
        self._finished_announced = False
        self._set_paused(False)
        if seconds == 0:
            self._running = False
            self._end_time = None
            self._show_remaining(0)
            self._announce_finished()
            return

        self._running = True
        self._end_time = self._clock() + seconds
        self._tick()

    def pause(self) -> None:
        """現在の残り時間を保持してカウントダウンを一時停止する。"""
        if not self._running or self._end_time is None:
            return

        remaining = max(0, int(self._end_time - self._clock() + 0.999999))
        self._cancel_scheduled_update()
        self._running = False
        self._end_time = None
        self._remaining_seconds = remaining
        self._show_remaining(remaining)
        if remaining == 0:
            self._announce_finished()
            return
        self._set_paused(True)

    def _resume(self) -> None:
        """一時停止中の残り時間からカウントダウンを再開する。"""
        self._set_paused(False)
        if self._remaining_seconds == 0:
            self._show_remaining(0)
            self._announce_finished()
            return
        self._running = True
        self._end_time = self._clock() + self._remaining_seconds
        self._tick()

    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.start_button.configure(text="再開" if paused else "スタート")
        self.pause_button.configure(state=tk.DISABLED if paused else tk.NORMAL)

    def reset(self) -> None:
        """タイマーを停止し、既定の120秒表示に戻す。"""
        self._cancel_scheduled_update()
        self._running = False
        self._end_time = None
        self._remaining_seconds = self.DEFAULT_SECONDS
        self._finished_announced = False
        self._set_paused(False)
        self.seconds_var.set(str(self.DEFAULT_SECONDS))
        self._show_remaining(self._remaining_seconds)

    def update(self) -> None:
        """入力値を表示用ウィンドウへ反映する（タイマーは開始しない）。"""
        seconds = self._get_input_seconds()
        if seconds is None:
            return
        self._cancel_scheduled_update()
        self._running = False
        self._end_time = None
        self._remaining_seconds = seconds
        self._finished_announced = False
        self._set_paused(False)
        self._show_remaining(seconds)

    def _get_input_seconds(self) -> Optional[int]:
        try:
            return self.parse_seconds(self.seconds_var.get())
        except ValueError as error:
            messagebox.showerror("入力エラー", str(error), parent=self.root)
            self.seconds_entry.focus_set()
            return None

    def _tick(self) -> None:
        if not self._running or self._end_time is None:
            return

        # 少数秒が残っていても、表示は切り上げて残り秒数を示す。
        remaining = max(0, int(self._end_time - self._clock() + 0.999999))
        # 0秒への遷移は終了ブザーのみとし、「ピッ」音は鳴らさない。
        tick_count = max(0, self._remaining_seconds - max(remaining, 1))
        for _ in range(tick_count):
            self._play_tick_sound()
        self._remaining_seconds = remaining
        self._show_remaining(remaining)
        if remaining == 0:
            self._running = False
            self._end_time = None
            self._after_id = None
            self._announce_finished()
            return
        self._after_id = self.root.after(100, self._tick)

    def _show_remaining(self, seconds: int) -> None:
        self.timer_label.configure(text=self.format_seconds(seconds))
        if seconds == 0:
            self.display.configure(background=self.FINISHED_BACKGROUND)
            self.timer_label.configure(
                background=self.FINISHED_BACKGROUND, foreground=self.WARNING_FOREGROUND
            )
        else:
            foreground = (
                self.WARNING_FOREGROUND if seconds <= 10 else self.NORMAL_FOREGROUND
            )
            self.display.configure(background=self.NORMAL_BACKGROUND)
            self.timer_label.configure(
                background=self.NORMAL_BACKGROUND, foreground=foreground
            )

    def _play_tick_sound(self) -> None:
        """カウントが1減るごとに約1000Hzの短音を鳴らす。"""
        self._play_tone(
            self.TICK_FREQUENCY_HZ,
            self.TICK_DURATION_MS,
            self.tick_volume_var.get(),
        )

    def _announce_finished(self) -> None:
        """終了を一度だけブザー音で通知する。"""
        if self._finished_announced:
            return
        self._finished_announced = True
        self._play_tone(
            self.FINISHED_FREQUENCY_HZ,
            self.FINISHED_DURATION_MS,
            self.finished_volume_var.get(),
            waveform="square",
        )

    def _play_tone(
        self,
        frequency_hz: int,
        duration_ms: int,
        volume: int,
        *,
        waveform: str = "sine",
    ) -> None:
        """指定した周波数・時間・音量のPCM音をWindowsスピーカーで再生する。"""
        if sys.platform != "win32":
            return

        volume = self.parse_volume(volume)
        command = (
            f"$frequency = {frequency_hz}; $duration = {duration_ms}; $volume = {volume}; "
            "$sampleRate = 44100; $sampleCount = [int]($sampleRate * $duration / 1000); "
            "$stream = New-Object System.IO.MemoryStream; "
            "$writer = New-Object System.IO.BinaryWriter($stream); "
            "$writer.Write([Text.Encoding]::ASCII.GetBytes('RIFF')); "
            "$writer.Write([int](36 + $sampleCount * 2)); "
            "$writer.Write([Text.Encoding]::ASCII.GetBytes('WAVEfmt ')); "
            "$writer.Write([int]16); $writer.Write([int16]1); $writer.Write([int16]1); "
            "$writer.Write([int]$sampleRate); $writer.Write([int]($sampleRate * 2)); "
            "$writer.Write([int16]2); $writer.Write([int16]16); "
            "$writer.Write([Text.Encoding]::ASCII.GetBytes('data')); "
            "$writer.Write([int]($sampleCount * 2)); "
            "for ($i = 0; $i -lt $sampleCount; $i++) { "
            "$wave = [Math]::Sin(2 * [Math]::PI * $frequency * $i / $sampleRate); "
            f"if ('{waveform}' -eq 'square') {{ if ($wave -ge 0) {{ $wave = 1 }} else {{ $wave = -1 }} }}; "
            "$sample = [int16]($wave * 32767 * $volume / 100); "
            "$writer.Write($sample) }; $writer.Flush(); $stream.Position = 0; "
            "$player = [System.Media.SoundPlayer]::new($stream); $player.PlaySync()"
        )
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", command],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (FileNotFoundError, OSError):
            # 音声出力を利用できない場合でも、カウントダウン終了は維持する。
            pass

    def _resize_font(self, event: tk.Event) -> None:
        """表示領域の横幅のおよそ80%を占めるフォントサイズに調整する。"""
        font_size = max(12, int(event.width * 0.8 / 5))
        self.timer_label.configure(font=("Arial", font_size, "bold"))

    def _cancel_scheduled_update(self) -> None:
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def close(self) -> None:
        """予約済み処理を取り消し、両方のウィンドウを閉じる。"""
        self._cancel_scheduled_update()
        self._running = False
        self.root.destroy()

    def run(self) -> None:
        """GUIイベントループを開始する。"""
        self.root.mainloop()


if __name__ == "__main__":
    Calibration().run()

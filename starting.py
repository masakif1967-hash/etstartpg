"""ETロボコン「Go to the Start」用の開始合図・カウントアップ表示。"""

from __future__ import annotations

from array import array
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional
import wave

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame
from imageio_ffmpeg import get_ffmpeg_exe


class Stating:
    """開始合図MP4の最後の「Go」に同期してカウントアップするGUI。"""

    DEFAULT_SECONDS = 120
    MIN_SECONDS = 0
    MAX_SECONDS = 120
    DEFAULT_VOLUME = 30
    SAMPLE_RATE = 44_100
    MIXER_BUFFER_SIZE = 512
    CUE_ANALYSIS_WINDOW_SECONDS = 0.02
    WORD_GAP_SECONDS = 0.12
    CUE_SEARCH_SECONDS = 10.0
    # 添付音源の末尾「Go」の発話長（開始位置から言い終わりまで）。
    LAST_GO_DURATION_SECONDS = 0.3
    AUDIO_FILE_NAME = "ETロボコン120秒（スタート合図から120秒タイムアップ）.mp4"
    NORMAL_BACKGROUND = "black"
    FINISHED_BACKGROUND = "red"
    NORMAL_FOREGROUND = "white"
    WARNING_FOREGROUND = "yellow"
    # ラップ表示時、従来のタイム文字サイズを100%として縮小する。
    LAP_TIMER_FONT_RATIO = 0.6
    LAP_LINE_FONT_RATIO = 0.4

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._running = False
        self._timer_started_at: Optional[float] = None
        self._after_id: Optional[str] = None
        self._cue_after_id: Optional[str] = None
        self._duration_seconds = self.DEFAULT_SECONDS
        self._audio_available = False
        self._audio_error: Optional[str] = None
        self._cue_seconds: Optional[float] = None
        self._audio_sound: Optional[pygame.mixer.Sound] = None
        self._audio_channel: Optional[pygame.mixer.Channel] = None
        self._wav_path: Optional[Path] = None
        self._lap_seconds: Optional[float] = None
        self._display_width = 320

        self.root = root if root is not None else tk.Tk()
        self.root.title("Go to the Start 操作")
        self.root.resizable(False, False)
        self.root.option_add("*Font", "{Yu Gothic UI} 12")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._load_mp4_audio()
        self._build_control_window()
        self._build_display_window()
        self._show_elapsed(0.0)

    def _build_control_window(self) -> None:
        frame = tk.Frame(self.root, padx=16, pady=16)
        frame.grid(sticky="nsew")

        tk.Label(frame, text="カウントアップ時間（秒）").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        self.seconds_var = tk.StringVar(value=str(self.DEFAULT_SECONDS))
        self.seconds_entry = tk.Entry(frame, textvariable=self.seconds_var, width=10)
        self.seconds_entry.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 12))

        tk.Label(frame, text="音量").grid(row=2, column=0, columnspan=3, sticky="w")
        self.volume_var = tk.IntVar(value=self.DEFAULT_VOLUME)
        self.volume_scale = tk.Scale(
            frame,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self._change_volume,
        )
        self.volume_scale.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._bind_lap_key(self.volume_scale)

        self.start_button = tk.Button(frame, text="スタート", command=self.start)
        self.start_button.grid(row=4, column=0, padx=(0, 4))
        self.reset_button = tk.Button(frame, text="リセット", command=self.reset)
        self.reset_button.grid(row=4, column=1, padx=4)
        self.update_button = tk.Button(frame, text="更新", command=self.update)
        self.update_button.grid(row=4, column=2, padx=(4, 0))
        self.lap_button = tk.Button(frame, text="Lap", command=self.record_lap)
        self.lap_button.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for widget in (
            self.root,
            self.seconds_entry,
            self.start_button,
            self.reset_button,
            self.update_button,
            self.lap_button,
        ):
            self._bind_lap_key(widget)

    def _build_display_window(self) -> None:
        self.display = tk.Toplevel(self.root)
        self.display.title("Go to the Start 表示")
        self.display.configure(background=self.NORMAL_BACKGROUND)
        self.display.minsize(320, 180)
        self.display.protocol("WM_DELETE_WINDOW", self.close)

        self.content = tk.Frame(self.display, background=self.NORMAL_BACKGROUND)
        self.content.pack(expand=True)

        self.timer_label = tk.Label(
            self.content,
            background=self.NORMAL_BACKGROUND,
            foreground=self.NORMAL_FOREGROUND,
            font=("Arial", 64, "bold"),
        )
        self.timer_label.pack()
        self.lap_label = tk.Label(
            self.content,
            background=self.NORMAL_BACKGROUND,
            foreground=self.NORMAL_FOREGROUND,
            font=("Arial", 24, "bold"),
        )
        self.display.bind("<Configure>", self._resize_font)
        self._bind_lap_key(self.display)

    @classmethod
    def parse_seconds(cls, value: str) -> int:
        try:
            seconds = int(value.strip())
        except (AttributeError, ValueError):
            raise ValueError("カウントアップ時間は0～120の整数で入力してください。") from None
        if not cls.MIN_SECONDS <= seconds <= cls.MAX_SECONDS:
            raise ValueError("カウントアップ時間は0～120の範囲で入力してください。")
        return seconds

    @staticmethod
    def format_elapsed(seconds: float) -> str:
        return f"{max(0.0, seconds):05.1f}"

    @classmethod
    def detect_last_go_cue(cls, wav_path: Path) -> float:
        """開始アナウンス内の最後の「Go」を言い終わる時刻を検出する。"""
        with wave.open(str(wav_path), "rb") as wav_file:
            if wav_file.getsampwidth() != 2 or wav_file.getnchannels() != 1:
                raise ValueError("解析用WAVは16bitモノラルである必要があります。")
            sample_rate = wav_file.getframerate()
            samples = array("h")
            samples.frombytes(wav_file.readframes(wav_file.getnframes()))
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            raise ValueError("音声データがありません。")

        window_size = max(1, round(sample_rate * cls.CUE_ANALYSIS_WINDOW_SECONDS))
        peak = max(abs(sample) for sample in samples)
        threshold = max(400, int(peak * 0.06))
        word_gap_windows = max(1, round(cls.WORD_GAP_SECONDS / cls.CUE_ANALYSIS_WINDOW_SECONDS))
        search_sample_count = min(len(samples), round(sample_rate * cls.CUE_SEARCH_SECONDS))

        silent_windows = 0
        latest_word_started_at: Optional[float] = None
        for offset in range(0, search_sample_count, window_size):
            window = samples[offset : offset + window_size]
            active = max(abs(sample) for sample in window) >= threshold
            timestamp = offset / sample_rate
            if active:
                if latest_word_started_at is None or silent_windows >= word_gap_windows:
                    latest_word_started_at = timestamp
                silent_windows = 0
            else:
                silent_windows += 1
        if latest_word_started_at is None:
            raise ValueError("開始アナウンスの発声音を検出できませんでした。")
        return latest_word_started_at + cls.LAST_GO_DURATION_SECONDS

    def _load_mp4_audio(self) -> None:
        """MP4をFFmpegでWAVへデコードし、再生音とGo合図時刻を準備する。"""
        mp4_path = Path(__file__).resolve().parent / "音声データ" / self.AUDIO_FILE_NAME
        if not mp4_path.is_file():
            self._audio_error = f"音声ファイルが見つかりません: {mp4_path}"
            return

        try:
            with tempfile.NamedTemporaryFile(prefix="et_start_", suffix=".wav", delete=False) as file:
                self._wav_path = Path(file.name)
            subprocess.run(
                [
                    get_ffmpeg_exe(), "-y", "-i", str(mp4_path), "-vn", "-ac", "1",
                    "-ar", str(self.SAMPLE_RATE), "-c:a", "pcm_s16le", str(self._wav_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                # FFmpegの出力エンコーディングは環境依存のため、CP932として
                # 復号しない。日本語ファイル名を含む環境でも安全に実行できる。
                stderr=subprocess.DEVNULL,
            )
            self._cue_seconds = self.detect_last_go_cue(self._wav_path)
            pygame.mixer.init(
                frequency=self.SAMPLE_RATE,
                size=-16,
                channels=1,
                buffer=self.MIXER_BUFFER_SIZE,
            )
            self._audio_sound = pygame.mixer.Sound(str(self._wav_path))
            self._audio_sound.set_volume(self.DEFAULT_VOLUME / 100)
            self._audio_available = True
        except (OSError, subprocess.CalledProcessError, pygame.error, ValueError) as error:
            self._audio_error = f"MP4の読み込みに失敗しました: {error}"
            self._cleanup_wav()

    def start(self) -> None:
        duration = self._get_input_seconds()
        if duration is None:
            return
        if not self._audio_available or self._audio_sound is None or self._cue_seconds is None:
            messagebox.showerror("音声読み込みエラー", self._audio_error or "MP4を読み込めません。", parent=self.root)
            return

        self._stop_timer()
        self._stop_audio()
        self._duration_seconds = duration
        self._show_elapsed(0.0)
        self._audio_sound.set_volume(self.volume_var.get() / 100)
        self._audio_channel = self._audio_sound.play()
        if self._audio_channel is None:
            messagebox.showerror("音声再生エラー", "MP4の再生を開始できません。", parent=self.root)
            return
        self._audio_channel.set_volume(self.volume_var.get() / 100)
        self._cue_after_id = self.root.after(round(self._cue_seconds * 1000), self._begin_countup)

    def reset(self) -> None:
        self._stop_timer()
        self._stop_audio()
        self._duration_seconds = self.DEFAULT_SECONDS
        self.seconds_var.set(str(self.DEFAULT_SECONDS))
        self._show_elapsed(0.0)

    def update(self) -> None:
        duration = self._get_input_seconds()
        if duration is None:
            return
        self._stop_timer()
        self._duration_seconds = duration
        self._show_elapsed(0.0)

    def _get_input_seconds(self) -> Optional[int]:
        try:
            return self.parse_seconds(self.seconds_var.get())
        except ValueError as error:
            messagebox.showerror("入力エラー", str(error), parent=self.root)
            self.seconds_entry.focus_set()
            return None

    def record_lap(self) -> None:
        """カウントアップ中の経過時間を、表示中タイムの直下へ出す。"""
        if not self._running or self._timer_started_at is None:
            return
        elapsed = min(float(self._duration_seconds), self._clock() - self._timer_started_at)
        self._lap_seconds = elapsed
        self.lap_label.configure(text=f"LAP TIME:{self.format_elapsed(elapsed)}")
        if not self.lap_label.winfo_manager():
            self.lap_label.pack()
        self._apply_fonts()

    def _clear_lap(self) -> None:
        self._lap_seconds = None
        self.lap_label.configure(text="")
        if self.lap_label.winfo_manager():
            self.lap_label.pack_forget()
        self._apply_fonts()

    def _on_space(self, _event: tk.Event) -> str:
        """スペースキーでラップを記録し、入力欄にはスペースを入れない。"""
        self.record_lap()
        return "break"

    def _bind_lap_key(self, widget: tk.Misc) -> None:
        widget.bind("<space>", self._on_space)

    def _change_volume(self, value: str) -> None:
        volume = max(0, min(100, int(float(value))))
        if self._audio_sound is not None:
            self._audio_sound.set_volume(volume / 100)
        if self._audio_channel is not None:
            self._audio_channel.set_volume(volume / 100)

    def _begin_countup(self) -> None:
        self._cue_after_id = None
        self._timer_started_at = self._clock()
        self._running = True
        self._tick()

    def _tick(self) -> None:
        if not self._running or self._timer_started_at is None:
            return
        elapsed = min(self._duration_seconds, self._clock() - self._timer_started_at)
        self._show_elapsed(elapsed)
        if elapsed >= self._duration_seconds:
            self._running = False
            self._timer_started_at = None
            self._after_id = None
            self._stop_audio()
            return
        self._after_id = self.root.after(50, self._tick)

    def _show_elapsed(self, elapsed: float) -> None:
        self.timer_label.configure(text=self.format_elapsed(elapsed))
        if elapsed >= self._duration_seconds and self._duration_seconds >= 0:
            background, foreground = self.FINISHED_BACKGROUND, self.WARNING_FOREGROUND
        elif self._duration_seconds - elapsed <= 10.0:
            background, foreground = self.NORMAL_BACKGROUND, self.WARNING_FOREGROUND
        else:
            background, foreground = self.NORMAL_BACKGROUND, self.NORMAL_FOREGROUND
        self.display.configure(background=background)
        self.content.configure(background=background)
        self.timer_label.configure(background=background, foreground=foreground)
        self.lap_label.configure(background=background, foreground=self.NORMAL_FOREGROUND)

    def _resize_font(self, event: tk.Event) -> None:
        if event.widget is not self.display:
            return
        self._display_width = max(1, int(event.width))
        self._apply_fonts()

    def _apply_fonts(self) -> None:
        """タイムは横幅の約80%を100%とし、ラップ表示中は60%と40%にする。"""
        base = max(12, int(self._display_width * 0.8 / 5))
        if self._lap_seconds is None:
            timer_size = base
        else:
            timer_size = max(1, int(base * self.LAP_TIMER_FONT_RATIO))
        lap_size = max(1, int(base * self.LAP_LINE_FONT_RATIO))
        self.timer_label.configure(font=("Arial", timer_size, "bold"))
        self.lap_label.configure(font=("Arial", lap_size, "bold"))

    def _stop_timer(self) -> None:
        self._running = False
        self._timer_started_at = None
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._cue_after_id is not None:
            try:
                self.root.after_cancel(self._cue_after_id)
            except tk.TclError:
                pass
            self._cue_after_id = None
        self._clear_lap()

    def _stop_audio(self) -> None:
        if self._audio_channel is not None:
            self._audio_channel.stop()
            self._audio_channel = None

    def _cleanup_wav(self) -> None:
        if self._wav_path is not None:
            try:
                self._wav_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._wav_path = None

    def close(self) -> None:
        self._stop_timer()
        self._stop_audio()
        if pygame.mixer.get_init() is not None:
            pygame.mixer.quit()
        self._cleanup_wav()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    Stating().run()

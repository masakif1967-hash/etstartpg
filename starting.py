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
from tkinter import font as tkfont
from tkinter import messagebox, ttk
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
    # タイムの文字サイズは従来の算出のままにする。
    LAP_FONT_RATIO = 0.85
    # 表示するラップタイムはタイムの50%。
    LAP_DISPLAY_RATIO = 0.5
    # フライングスタート1行 + 得点表7行 + 小計 + リザルトポイント。
    POINT_LINE_COUNT = 10
    DISPLAY_VERTICAL_MARGIN = 12
    RESULT_BASE = 35.0
    FLYING_START_POINTS = -35
    CHECKPOINT_POINTS = 2
    CHECKPOINT_MIN = 0
    CHECKPOINT_MAX = 3
    LAP_GATE_POINTS = 3
    FINISH_POINTS = 3
    FINISH_CONFIRM_MS = 3000
    BOTTLE_PUSH_POINTS = 5
    BOTTLE_DELIVERY_POINTS = 1
    BOTTLE_COLOR_POINTS = 5
    RALLY_POINTS = 5
    FLYING_START_TEXT = f"☑フライングスタート\u3000{FLYING_START_POINTS}ポイント"
    LAP_GATE_TEXT = f"☑Lapゲート到達 {LAP_GATE_POINTS}ポイント"
    FINISH_TEXT = f"フィニィッシュ\u3000{FINISH_POINTS}ポイント"
    BOTTLE_PUSH_TEXT = f"ボトル押し出し\u3000{BOTTLE_PUSH_POINTS}ポイント"
    BOTTLE_DELIVERY_TEXT = f"ボトル.デリバリー\u3000{BOTTLE_DELIVERY_POINTS}ポイント"
    BOTTLE_COLOR_TEXT = f"ボトル.色一致\u3000{BOTTLE_COLOR_POINTS}ポイント"

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
        self._display_height = 180
        self._finish_after_id: Optional[str] = None
        self._finish_pending = False
        self._finish_confirmed = False

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
            row=0, column=0, columnspan=4, sticky="w"
        )
        self.seconds_var = tk.StringVar(value=str(self.DEFAULT_SECONDS))
        self.seconds_entry = tk.Entry(frame, textvariable=self.seconds_var, width=10)
        self.seconds_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 12))

        tk.Label(frame, text="音量").grid(row=2, column=0, columnspan=4, sticky="w")
        self.volume_var = tk.IntVar(value=self.DEFAULT_VOLUME)
        self.volume_scale = tk.Scale(
            frame,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self._change_volume,
        )
        self.volume_scale.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(0, 10))

        self.start_button = tk.Button(frame, text="スタート", command=self.start)
        self.start_button.grid(row=4, column=0, padx=(0, 4))
        self.stop_button = tk.Button(frame, text="ストップ", command=self.stop)
        self.stop_button.grid(row=4, column=1, padx=4)
        self.reset_button = tk.Button(frame, text="リセット", command=self.reset)
        self.reset_button.grid(row=4, column=2, padx=4)
        self.update_button = tk.Button(frame, text="更新", command=self.update)
        self.update_button.grid(row=4, column=3, padx=(4, 0))

        self.flying_var = tk.BooleanVar(value=False)
        self.flying_check = tk.Checkbutton(
            frame,
            text="フライングスタート",
            variable=self.flying_var,
            command=self._update_flying_start,
        )
        self.flying_check.grid(row=5, column=0, columnspan=4, sticky="w", pady=(12, 4))

        checkpoint_row = tk.Frame(frame)
        checkpoint_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        tk.Label(checkpoint_row, text="チェックポイント到達").pack(side="left")
        self.checkpoint_var = tk.StringVar(value=str(self.CHECKPOINT_MIN))
        self.checkpoint_combo = ttk.Combobox(
            checkpoint_row,
            textvariable=self.checkpoint_var,
            values=[str(value) for value in range(self.CHECKPOINT_MIN, self.CHECKPOINT_MAX + 1)],
            width=4,
            state="readonly",
        )
        self.checkpoint_combo.pack(side="left", padx=(8, 0))

        self.lap_button = tk.Button(frame, text="Lap", command=self.record_lap)
        self.lap_button.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        self._build_score_controls(frame)
        for widget in (
            self.root,
            self.seconds_entry,
            self.volume_scale,
            self.start_button,
            self.stop_button,
            self.reset_button,
            self.update_button,
            self.flying_check,
            self.checkpoint_combo,
            self.lap_button,
            self.finish_button,
            self.finish_cancel_button,
            self.bottle_check,
            self.delivery_check,
            self.color_check,
            self.rally_combo,
        ):
            self._bind_lap_key(widget)

    def _build_score_controls(self, frame: tk.Frame) -> None:
        """Lapボタンの下へ、No.4以降の課題ポイント操作を1行ずつ置く。"""
        self.finish_button = tk.Button(frame, text="フィニィッシュ", command=self.press_finish)
        self.finish_button.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(12, 4))
        self.finish_cancel_button = tk.Button(
            frame, text="フィニィッシュキャンセル", command=self.cancel_finish
        )
        self.finish_cancel_button.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(4, 4))

        self.bottle_var = tk.BooleanVar(value=False)
        self.bottle_check = tk.Checkbutton(
            frame,
            text="ボトル押し出し",
            variable=self.bottle_var,
            command=self._refresh_score_table,
        )
        self.bottle_check.grid(row=10, column=0, columnspan=4, sticky="w", pady=(4, 4))

        self.delivery_var = tk.BooleanVar(value=False)
        self.delivery_check = tk.Checkbutton(
            frame,
            text="ボトルデリバリー.デリバリー",
            variable=self.delivery_var,
            command=self._refresh_score_table,
        )
        self.delivery_check.grid(row=11, column=0, columnspan=4, sticky="w", pady=(4, 4))

        self.color_var = tk.BooleanVar(value=False)
        self.color_check = tk.Checkbutton(
            frame,
            text="ボトルデリバリー.色一致",
            variable=self.color_var,
            command=self._refresh_score_table,
        )
        self.color_check.grid(row=12, column=0, columnspan=4, sticky="w", pady=(4, 4))

        rally_row = tk.Frame(frame)
        rally_row.grid(row=13, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        tk.Label(rally_row, text="ETラリー.1周回").pack(side="left")
        self.rally_var = tk.StringVar(value=str(self.CHECKPOINT_MIN))
        self.rally_combo = ttk.Combobox(
            rally_row,
            textvariable=self.rally_var,
            values=[str(value) for value in range(self.CHECKPOINT_MIN, self.CHECKPOINT_MAX + 1)],
            width=4,
            state="readonly",
        )
        self.rally_combo.pack(side="left", padx=(8, 0))

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
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        self.timer_label.grid(row=0, column=0)
        self.lap_label = self._make_score_label(1)
        self.lap_label.grid_remove()
        self.flying_label = self._make_score_label(2)
        self.flying_label.grid_remove()
        self._build_score_table()
        self.checkpoint_var.trace_add("write", self._refresh_score_table)
        self.rally_var.trace_add("write", self._refresh_score_table)
        self._refresh_score_table()
        self.display.bind("<Configure>", self._resize_font)
        self._bind_lap_key(self.display)

    def _make_score_label(self, row: int) -> tk.Label:
        label = tk.Label(
            self.content,
            background=self.NORMAL_BACKGROUND,
            foreground=self.NORMAL_FOREGROUND,
            font=("Yu Gothic UI", 24, "bold"),
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        label.grid(row=row, column=0)
        return label

    def _build_score_table(self) -> None:
        """チェックポイント到達以下を、枠線のない2列の表にする。"""
        self._display_background = self.NORMAL_BACKGROUND
        self.score_table = tk.Frame(
            self.content,
            background=self.NORMAL_BACKGROUND,
            borderwidth=0,
            highlightthickness=0,
        )
        self.score_table.grid(row=3, column=0, sticky="ew")
        self._item_rows = [self._make_table_row() for _ in range(7)]
        self._subtotal_name, self._subtotal_value = self._make_table_row()
        self._result_name, self._result_value = self._make_table_row()
        self._table_labels = [
            label
            for pair in (
                *self._item_rows,
                (self._subtotal_name, self._subtotal_value),
                (self._result_name, self._result_value),
            )
            for label in pair
        ]

    def _make_table_row(self) -> tuple[tk.Label, tk.Label]:
        name_label = tk.Label(
            self.score_table,
            background=self.NORMAL_BACKGROUND,
            foreground=self.NORMAL_FOREGROUND,
            font=("Yu Gothic UI", 24, "bold"),
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            anchor="w",
        )
        value_label = tk.Label(
            self.score_table,
            background=self.NORMAL_BACKGROUND,
            foreground=self.NORMAL_FOREGROUND,
            font=("Yu Gothic UI", 24, "bold"),
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            anchor="e",
        )
        return name_label, value_label

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
        """経過時間を ###.0 形式（先頭ゼロなし、小数1桁）で返す。"""
        return f"{max(0.0, seconds):.1f}"

    @classmethod
    def format_checkpoint(cls, count: int) -> str:
        points = count * cls.CHECKPOINT_POINTS
        return f"チェックポイント到達\u3000{count} 箇所\u3000 {points}ポイント"

    @classmethod
    def format_rally(cls, count: int) -> str:
        points = count * cls.RALLY_POINTS
        return f"ETラリー.{count}周回\u3000 {points}ポイント"

    @staticmethod
    def calculate_result(lap_seconds: float, subtotal: int) -> float:
        """35.0 からラップタイムを引き、小計を加えたリザルトポイント。"""
        return Stating.RESULT_BASE - max(0.0, lap_seconds) + subtotal

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

    def stop(self) -> None:
        """タイムカウントと音声再生を止める。表示中のタイムと得点は残す。"""
        if self._running and self._timer_started_at is not None:
            elapsed = min(float(self._duration_seconds), self._clock() - self._timer_started_at)
            self._show_elapsed(elapsed)
        self._running = False
        self._timer_started_at = None
        self._cancel_scheduled_updates()
        self._stop_audio()

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
            self.lap_label.grid()
        self._refresh_score_table()
        self._apply_fonts()

    def _clear_lap(self) -> None:
        self._lap_seconds = None
        self.lap_label.configure(text="")
        if self.lap_label.winfo_manager():
            self.lap_label.grid_remove()
        self._refresh_score_table()
        self._apply_fonts()

    def press_finish(self) -> None:
        """フィニィッシュ後、3秒間キャンセルされなければポイントを表示する。"""
        if self._finish_confirmed:
            return
        self._cancel_finish_wait()
        self._finish_pending = True
        self._finish_after_id = self.root.after(self.FINISH_CONFIRM_MS, self._confirm_finish)

    def cancel_finish(self) -> None:
        """待機中の確定を止め、表示中のフィニィッシュ行も消す。"""
        self._cancel_finish_wait()
        self._finish_confirmed = False
        self._refresh_score_table()

    def _confirm_finish(self) -> None:
        self._finish_after_id = None
        if not self._finish_pending:
            return
        self._finish_pending = False
        self._finish_confirmed = True
        self._refresh_score_table()

    def _cancel_finish_wait(self) -> None:
        self._finish_pending = False
        if self._finish_after_id is None:
            return
        try:
            self.root.after_cancel(self._finish_after_id)
        except tk.TclError:
            pass
        self._finish_after_id = None

    def _checkpoint_count(self) -> int:
        return self._selected_count(self.checkpoint_var)

    def _set_score_line(self, label: tk.Label, visible: bool, text: str) -> None:
        if visible:
            label.configure(text=text)
            if not label.winfo_manager():
                label.grid()
        elif label.winfo_manager():
            label.grid_remove()

    def _update_flying_start(self) -> None:
        """チェックONのとき、LAP TIMEの次の行へフライングスタートを出す。"""
        self._set_score_line(self.flying_label, self.flying_var.get(), self.FLYING_START_TEXT)

    def _score_table_entries(self) -> list[tuple[str, int]]:
        """表示中の得点行を、チェックポイント到達から順に返す。"""
        entries: list[tuple[str, int]] = []
        checkpoint_count = self._checkpoint_count()
        checkpoint_points = checkpoint_count * self.CHECKPOINT_POINTS
        if checkpoint_points > 0:
            entries.append((f"チェックポイント到達\u3000{checkpoint_count} 箇所", checkpoint_points))
        if self._lap_seconds is not None:
            entries.append(("☑Lapゲート到達", self.LAP_GATE_POINTS))
        if self._finish_confirmed:
            entries.append(("フィニィッシュ", self.FINISH_POINTS))
        if self.bottle_var.get():
            entries.append(("ボトル押し出し", self.BOTTLE_PUSH_POINTS))
        if self.delivery_var.get():
            entries.append(("ボトル.デリバリー", self.BOTTLE_DELIVERY_POINTS))
        if self.color_var.get():
            entries.append(("ボトル.色一致", self.BOTTLE_COLOR_POINTS))
        rally_count = self._rally_count()
        rally_points = rally_count * self.RALLY_POINTS
        if rally_points > 0:
            entries.append((f"ETラリー.{rally_count}周回", rally_points))
        return entries

    def _refresh_score_table(self, *_args: object) -> None:
        """得点行と、小計・リザルトポイントを最新の値で並べる。"""
        if not hasattr(self, "_item_rows"):
            return
        entries = self._score_table_entries()
        subtotal = sum(points for _, points in entries)
        for index, (name_label, value_label) in enumerate(self._item_rows):
            if index < len(entries):
                name, points = entries[index]
                self._show_table_row(name_label, value_label, index, name, str(points))
            else:
                self._hide_table_row(name_label, value_label)
        summary_row = len(entries)
        self._show_table_row(self._subtotal_name, self._subtotal_value, summary_row, "小計", str(subtotal))
        lap_seconds = 0.0 if self._lap_seconds is None else self._lap_seconds
        result = self.calculate_result(lap_seconds, subtotal)
        self._show_table_row(
            self._result_name,
            self._result_value,
            summary_row + 1,
            "リザルトポイント",
            f"{result:.1f}",
        )
        self._apply_score_colors()

    def _show_table_row(
        self,
        name_label: tk.Label,
        value_label: tk.Label,
        row: int,
        name: str,
        value: str,
    ) -> None:
        name_label.configure(text=name)
        value_label.configure(text=value)
        name_label.grid(row=row, column=0, sticky="w")
        value_label.grid(row=row, column=1, sticky="e", padx=(24, 0))

    def _hide_table_row(self, name_label: tk.Label, value_label: tk.Label) -> None:
        if name_label.winfo_manager():
            name_label.grid_remove()
        if value_label.winfo_manager():
            value_label.grid_remove()

    def _apply_score_colors(self) -> None:
        background = self._display_background
        self.score_table.configure(background=background)
        for name_label, value_label in (*self._item_rows, (self._subtotal_name, self._subtotal_value)):
            for label in (name_label, value_label):
                label.configure(background=background, foreground=self.NORMAL_FOREGROUND)
        for label in (self._result_name, self._result_value):
            label.configure(background=background, foreground=self.WARNING_FOREGROUND)

    def _rally_count(self) -> int:
        return self._selected_count(self.rally_var)

    def _selected_count(self, variable: tk.StringVar) -> int:
        try:
            count = int(variable.get())
        except (TypeError, ValueError):
            return self.CHECKPOINT_MIN
        return min(self.CHECKPOINT_MAX, max(self.CHECKPOINT_MIN, count))

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
        self._display_background = background
        self.display.configure(background=background)
        self.content.configure(background=background)
        self.timer_label.configure(background=background, foreground=foreground)
        self.lap_label.configure(background=background, foreground=self.NORMAL_FOREGROUND)
        self.flying_label.configure(background=background, foreground=self.NORMAL_FOREGROUND)
        self._apply_score_colors()

    def _resize_font(self, event: tk.Event) -> None:
        if event.widget is not self.display:
            return
        self._display_width = max(1, int(event.width))
        self._display_height = max(1, int(event.height))
        self._apply_fonts()

    def _apply_fonts(self) -> None:
        """タイムは従来サイズ、LAP TIME はその50%、他8行は縦幅に収める。"""
        width_limit = max(1, int(self._display_width * 0.92))
        height_budget = max(self.POINT_LINE_COUNT, self._display_height - self.DISPLAY_VERTICAL_MARGIN)
        timer_size = max(1, int(self._display_width * 0.8 / 5))
        lap_limit = self._largest_fitting_size("Arial", "LAP TIME:120.0", width_limit)
        if lap_limit > 1:
            timer_size = min(timer_size, max(1, int(lap_limit / self.LAP_FONT_RATIO)))
        timer_size, lap_size = self._fit_timer_and_lap(timer_size, height_budget)
        timer_height = self._line_space("Arial", timer_size)
        lap_height = self._line_space("Arial", lap_size)
        remaining = max(1, height_budget - timer_height - lap_height)
        point_size = min(lap_size, self._fit_point_font(remaining, width_limit))
        lap_display_size = max(1, round(timer_size * self.LAP_DISPLAY_RATIO))
        self.timer_label.configure(font=("Arial", timer_size, "bold"))
        self.lap_label.configure(font=("Arial", lap_display_size, "bold"))
        self.flying_label.configure(font=("Yu Gothic UI", point_size, "bold"))
        for label in self._table_labels:
            label.configure(font=("Yu Gothic UI", point_size, "bold"))

    def _fit_timer_and_lap(self, timer_size: int, height_budget: int) -> tuple[int, int]:
        """タイムと LAP TIME を、8行分の高さを残せるサイズまで縮める。"""
        timer_size = max(1, timer_size)
        minimum_point_height = self._line_space("Yu Gothic UI", 1) * self.POINT_LINE_COUNT
        while True:
            lap_size = max(1, int(timer_size * self.LAP_FONT_RATIO))
            if timer_size > 1:
                lap_size = min(lap_size, timer_size - 1)
            timer_height = self._line_space("Arial", timer_size)
            lap_height = self._line_space("Arial", lap_size)
            fits = timer_height + lap_height + minimum_point_height <= height_budget
            if fits or timer_size == 1:
                return timer_size, lap_size
            timer_size -= 1

    def _fit_point_font(self, remaining_height: int, width_limit: int) -> int:
        """得点表を含む行が縦幅と横幅に収まる文字サイズを返す。"""
        samples = (
            self.FLYING_START_TEXT,
            f"チェックポイント到達\u3000{self.CHECKPOINT_MAX} 箇所  {self.CHECKPOINT_MAX * self.CHECKPOINT_POINTS}",
            "リザルトポイント  -85.0",
            self.format_rally(self.CHECKPOINT_MAX),
        )
        size = max(1, remaining_height // self.POINT_LINE_COUNT)
        while size > 1:
            if self._line_space("Yu Gothic UI", size) * self.POINT_LINE_COUNT > remaining_height:
                size -= 1
                continue
            if all(self._text_width("Yu Gothic UI", size, sample) <= width_limit for sample in samples):
                return size
            size -= 1
        return 1

    def _largest_fitting_size(self, family: str, text: str, width_limit: int) -> int:
        low, high = 1, max(1, width_limit)
        best = 1
        while low <= high:
            mid = (low + high) // 2
            if self._text_width(family, mid, text) <= width_limit:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best

    def _line_space(self, family: str, size: int) -> int:
        return int(self._bold_font(family, size).metrics("linespace"))

    def _text_width(self, family: str, size: int, text: str) -> int:
        return int(self._bold_font(family, size).measure(text))

    def _bold_font(self, family: str, size: int) -> tkfont.Font:
        cache = getattr(self, "_font_cache", None)
        if cache is None:
            cache = {}
            self._font_cache = cache
        font = cache.get(family)
        if font is None:
            font = tkfont.Font(root=self.display, family=family, size=max(1, size), weight="bold")
            cache[family] = font
        else:
            font.configure(size=max(1, size))
        return font

    def _stop_timer(self) -> None:
        self._running = False
        self._timer_started_at = None
        self._cancel_scheduled_updates()
        self._clear_lap()

    def _cancel_scheduled_updates(self) -> None:
        for attribute in ("_after_id", "_cue_after_id"):
            after_id = getattr(self, attribute)
            if after_id is None:
                continue
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
            setattr(self, attribute, None)

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
        self._cancel_finish_wait()
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

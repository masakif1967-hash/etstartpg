"""result.json からゲーム順位と総合順位を表示する。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any


RESULT_FILE = Path(__file__).resolve().parent / "result.json"
GAME_SCORE_BASE = 73.0
MODEL_SCORE_WEIGHT = 7.0
GAME_SCORE_WEIGHT = 3.0


@dataclass(frozen=True)
class TeamResult:
    """1チーム分の入力値と計算済みスコア。"""

    name: str
    model_score: float
    game_l_score: float
    game_r_score: float
    game_score_av: float
    game_score: float
    total_score: float


def weighted_harmonic_mean(model_score: float, game_score: float) -> float:
    """model_score:game_score = 7:3 の重み付き調和平均を返す。"""

    if model_score == 0.0 or game_score == 0.0:
        return 0.0
    return (MODEL_SCORE_WEIGHT + GAME_SCORE_WEIGHT) / (
        (MODEL_SCORE_WEIGHT / model_score) + (GAME_SCORE_WEIGHT / game_score)
    )


def require_score(item: dict[str, Any], key: str, team_name: str) -> float:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{team_name} の {key} は数値にしてください。")
    score = float(value)
    if score < 0.0:
        raise ValueError(f"{team_name} の {key} は0以上の数値にしてください。")
    return score


def load_results(path: Path = RESULT_FILE) -> list[TeamResult]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"{path.name} を読み込めません: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} のJSONが不正です: {error}") from error

    teams = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(teams, list) or not teams:
        raise ValueError(f"{path.name} の teams にチームを1件以上入れてください。")

    results: list[TeamResult] = []
    seen: set[str] = set()
    for item in teams:
        if not isinstance(item, dict):
            raise ValueError("チームの定義が不正です。")

        name = item.get("TeamName")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("TeamName は空でない文字列にしてください。")
        name = name.strip()
        if name in seen:
            raise ValueError(f"TeamName が重複しています: {name}")

        model_score = require_score(item, "model_score", name)
        game_l_score = require_score(item, "gameL_score", name)
        game_r_score = require_score(item, "gameR_score", name)
        game_score_av = (game_l_score + game_r_score) / 2.0
        game_score = game_score_av / GAME_SCORE_BASE * 100.0
        total_score = weighted_harmonic_mean(model_score, game_score)

        results.append(
            TeamResult(
                name=name,
                model_score=model_score,
                game_l_score=game_l_score,
                game_r_score=game_r_score,
                game_score_av=game_score_av,
                game_score=game_score,
                total_score=total_score,
            )
        )
        seen.add(name)

    return results


def format_score(score: float) -> str:
    return f"{score:.2f}"


def print_game_ranking(results: list[TeamResult]) -> None:
    print("game順位")
    for rank, result in enumerate(sorted(results, key=lambda team: team.game_score_av, reverse=True), start=1):
        print(
            rank,
            result.name,
            format_score(result.game_l_score),
            format_score(result.game_r_score),
            format_score(result.game_score_av),
            sep="\t",
        )


def print_total_ranking(results: list[TeamResult]) -> None:
    print("総合順位")
    for rank, result in enumerate(sorted(results, key=lambda team: team.total_score, reverse=True), start=1):
        print(
            rank,
            result.name,
            format_score(result.model_score),
            format_score(result.game_score),
            format_score(result.total_score),
            sep="\t",
        )


def main() -> int:
    try:
        results = load_results()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    print_game_ranking(results)
    print_total_ranking(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

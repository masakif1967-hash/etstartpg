"""result.json からゲーム順位と総合順位を表示する。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


RESULT_FILE = Path(__file__).resolve().parent / "result.json"
PRESENTATION_FILE = Path(__file__).resolve().parent / "結果発表.pptx"
GAME_SCORE_BASE = 73.0
MODEL_SCORE_WEIGHT = 7.0
GAME_SCORE_WEIGHT = 3.0
GAME_RANKING_OBJECT_IDS = ("64", "65", "66")
TOTAL_RANKING_OBJECT_IDS = ("71", "72", "73")
PPTX_NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

for prefix, uri in PPTX_NAMESPACES.items():
    ET.register_namespace(prefix, uri)


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


def game_ranking(results: list[TeamResult]) -> list[TeamResult]:
    return sorted(results, key=lambda team: team.game_score_av, reverse=True)


def total_ranking(results: list[TeamResult]) -> list[TeamResult]:
    return sorted(results, key=lambda team: team.total_score, reverse=True)


def print_game_ranking(results: list[TeamResult]) -> None:
    print("game順位")
    for rank, result in enumerate(game_ranking(results), start=1):
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
    for rank, result in enumerate(total_ranking(results), start=1):
        print(
            rank,
            result.name,
            format_score(result.model_score),
            format_score(result.game_score),
            format_score(result.total_score),
            sep="\t",
        )


def set_shape_text(shape: ET.Element, text: str, target_name: str) -> None:
    text_runs = shape.findall(".//a:t", PPTX_NAMESPACES)
    if not text_runs:
        raise ValueError(f"{target_name} に書き換え可能なテキストがありません。")
    text_runs[0].text = text
    for text_run in text_runs[1:]:
        text_run.text = ""


def set_shape_text_by_id(root: ET.Element, object_id: str, text: str) -> bool:
    for shape in root.findall(".//p:sp", PPTX_NAMESPACES):
        c_nv_pr = shape.find(".//p:cNvPr", PPTX_NAMESPACES)
        if c_nv_pr is None or c_nv_pr.get("id") != object_id:
            continue

        set_shape_text(shape, text, f"オブジェクトID {object_id}")
        return True
    return False


def set_team_text_by_position(root: ET.Element, names: list[str]) -> None:
    text_shapes = [
        shape
        for shape in root.findall(".//p:sp", PPTX_NAMESPACES)
        if shape.findall(".//a:t", PPTX_NAMESPACES)
    ]
    if len(text_shapes) < len(names):
        raise ValueError("チーム名を書き込むテキストオブジェクトが足りません。")

    # PowerPointで再保存されるとオブジェクトIDが変わる場合があるため、
    # このテンプレートでチーム名欄に該当する末尾3つのテキスト図形へ書き込む。
    for shape, name in zip(text_shapes[-len(names) :], names):
        set_shape_text(shape, name, "チーム名欄")


def update_slide_text(zip_file: ZipFile, slide_path: str, replacements: dict[str, str]) -> bytes:
    root = ET.fromstring(zip_file.read(slide_path))
    missing_ids: list[str] = []
    for object_id, text in replacements.items():
        if not set_shape_text_by_id(root, object_id, text):
            missing_ids.append(object_id)
    if missing_ids:
        set_team_text_by_position(root, list(replacements.values()))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_presentation_rankings(
    results: list[TeamResult],
    path: Path = PRESENTATION_FILE,
) -> None:
    if len(results) < 3:
        raise ValueError("結果発表.pptx に書き込むにはチームが3件以上必要です。")
    if not path.is_file():
        raise ValueError(f"{path.name} が見つかりません。")

    game_names = [team.name for team in game_ranking(results)[:3]]
    total_names = [team.name for team in total_ranking(results)[:3]]
    replacements_by_slide = {
        "ppt/slides/slide2.xml": dict(zip(GAME_RANKING_OBJECT_IDS, game_names)),
        "ppt/slides/slide3.xml": dict(zip(TOTAL_RANKING_OBJECT_IDS, total_names)),
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with ZipFile(path, "r") as source, ZipFile(temp_path, "w", ZIP_DEFLATED) as destination:
            updated_slides = {
                slide_path: update_slide_text(source, slide_path, replacements)
                for slide_path, replacements in replacements_by_slide.items()
            }
            for item in source.infolist():
                content = updated_slides.get(item.filename)
                if content is None:
                    content = source.read(item.filename)
                destination.writestr(item, content)
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def main() -> int:
    try:
        results = load_results()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    print_game_ranking(results)
    print_total_ranking(results)
    try:
        write_presentation_rankings(results)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

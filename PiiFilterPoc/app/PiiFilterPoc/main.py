"""Excel のシートを Bedrock Guardrails でマスクし、マスク済みデータを Claude で処理する。

処理の流れ:
  1. シートを TSV テキストにする
  2. ApplyGuardrail (INPUT) でマスクする
  3. マスク済みデータだけを Converse (jp. 推論プロファイル) で Claude に渡す
  4. Claude の応答を ApplyGuardrail (OUTPUT) でチェックする
"""
from __future__ import annotations

import base64
import io
import os
import re
import zipfile
from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from botocore.config import Config
from openpyxl import Workbook, load_workbook

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
    from mypy_boto3_bedrock_runtime.type_defs import (
        ApplyGuardrailResponseTypeDef,
        ConverseResponseTypeDef,
        GuardrailUsageTypeDef,
        TokenUsageTypeDef,
    )

REGION: str = os.environ.get("AWS_REGION", "ap-northeast-1")
GUARDRAIL_ID: str = os.environ["GUARDRAIL_ID"]
GUARDRAIL_VERSION: str = os.environ.get("GUARDRAIL_VERSION", "1")
MODEL_ID: str = os.environ.get("MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")

# 1 回の ApplyGuardrail で送る量を抑えるための目安 (秒間クォータに収まることを保証するものではない)
MAX_CHUNK_CHARS: int = 12_000
# PoC の入力の上限。超えたらマスクする前にエラーにする
MAX_FILE_BYTES: int = 1_000_000
MAX_UNCOMPRESSED_BYTES: int = 20_000_000
MAX_CELLS: int = 10_000
MAX_CELL_CHARS: int = MAX_CHUNK_CHARS
MAX_INSTRUCTION_CHARS: int = 2_000
DEFAULT_INSTRUCTION: str = "このデータの傾向を要約してください。"
SYSTEM_PROMPT: str = (
    "あなたは表データを分析するアシスタントです。"
    "データ中の {NAME} や {EMAIL} などは、個人情報をマスクしたプレースホルダーです。"
    "{PHONE}{JP_PHONE} のようにプレースホルダーが連続している場合は、1 つの値が複数のフィルターで検出されたことを表します。"
    "マスクされた値を推測したり復元したりしないでください。"
)
PLACEHOLDER: re.Pattern[str] = re.compile(r"\{([A-Z0-9_]+)\}")

GuardrailSource = Literal["INPUT", "OUTPUT"]


class InvokePayload(TypedDict):
    filename: str
    content_base64: str
    instruction: NotRequired[str]


class Detection(TypedDict):
    filter: Literal["PII", "REGEX"]
    type: str
    match: str
    action: str


class CellResult(TypedDict):
    original: str
    masked: str
    types: list[str]


class MappedRow(TypedDict):
    mapped: Literal[True]
    cells: list[CellResult]


class UnmappedRow(TypedDict):
    mapped: Literal[False]
    original: list[str]
    masked_line: str | None


class SheetResult(TypedDict):
    name: str
    rows: list[MappedRow | UnmappedRow]
    detections: list[Detection]


class InstructionResult(TypedDict):
    masked: str
    detections: list[Detection]


class ClaudeResult(TypedDict):
    model_id: str
    answer: str
    answer_masked: str
    detections: list[Detection]
    usage: TokenUsageTypeDef


class InvokeResult(TypedDict):
    filename: str
    sheets: list[SheetResult]
    instruction: InstructionResult
    claude: ClaudeResult
    guardrail_usage: dict[str, int]


bedrock: BedrockRuntimeClient = boto3.client(
    "bedrock-runtime", region_name=REGION, config=Config(retries={"mode": "adaptive", "max_attempts": 6})
)
app: BedrockAgentCoreApp = BedrockAgentCoreApp()


def to_cell_text(value: object) -> str:
    if value is None:
        return ""
    # TSV の区切りを壊さないよう、セル内の改行とタブは空白にする
    return re.sub(r"[\t\r\n]+", " ", str(value)).strip()


def add_usage(total: dict[str, int], usage: GuardrailUsageTypeDef) -> None:
    for key, value in usage.items():
        if isinstance(value, int):
            total[key] = total.get(key, 0) + value


def apply_guardrail_blocks(
    texts: list[str], source: GuardrailSource, usage_total: dict[str, int]
) -> tuple[list[str] | None, list[Detection]]:
    """テキストをそれぞれ別のコンテンツブロックにして ApplyGuardrail を呼び、(ブロックごとのマスク後テキスト, 検出リスト) を返す。

    outputs の数がブロックの数と一致しないときは、マスク後テキストを None にする。
    """
    res: ApplyGuardrailResponseTypeDef = bedrock.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,
        content=[{"text": {"text": text}} for text in texts],
    )
    add_usage(usage_total, res["usage"])

    masked: list[str] | None = texts
    if res["action"] == "GUARDRAIL_INTERVENED":
        outputs: list[str] = [output.get("text", "") for output in res["outputs"]]
        masked = None
        if len(outputs) == len(texts):
            masked = outputs

    detections: list[Detection] = []
    for assessment in res["assessments"]:
        policy = assessment.get("sensitiveInformationPolicy")
        if policy is None:
            continue
        for entity in policy.get("piiEntities", []):
            detections.append({"filter": "PII", "type": entity["type"], "match": entity["match"], "action": entity["action"]})
        for regex in policy.get("regexes", []):
            detections.append({"filter": "REGEX", "type": regex["name"], "match": regex["match"], "action": regex["action"]})
    return masked, detections


def apply_guardrail(text: str, source: GuardrailSource, usage_total: dict[str, int]) -> tuple[str, list[Detection]]:
    """ApplyGuardrail を呼び、(マスク後テキスト, 検出リスト) を返す。"""
    if not text.strip():
        return text, []

    masked, detections = apply_guardrail_blocks([text], source, usage_total)
    if masked is None:
        raise RuntimeError("ApplyGuardrail の outputs の数がコンテンツの数と一致しません")
    return masked[0], detections


def chunk_blocks(blocks: list[str]) -> Iterator[range]:
    """ブロックを MAX_CHUNK_CHARS 以下のまとまりに分け、まとまりごとに添字の範囲を返す。"""
    start: int = 0
    size: int = 0
    for i, block in enumerate(blocks):
        if i > start and size + len(block) > MAX_CHUNK_CHARS:
            yield range(start, i)
            start = i
            size = 0
        size += len(block)
    if start < len(blocks):
        yield range(start, len(blocks))


def find_placeholders(original: str, masked: str) -> list[str]:
    """マスクで置き換わったセルについて、プレースホルダーの種類を返す。"""
    if original == masked:
        return []
    return PLACEHOLDER.findall(masked)


def read_sheets(excel_bytes: bytes) -> list[tuple[str, list[list[str]]]]:
    """Excel を読み込み、シートごとに (シート名, セルの文字列) を返す。上限を超えたら ValueError にする。"""
    if len(excel_bytes) > MAX_FILE_BYTES:
        raise ValueError(f"ファイルサイズが上限 ({MAX_FILE_BYTES} バイト) を超えています")
    # xlsx は zip なので、小さなファイルでも展開すると大きくなることがある。読み込む前に展開後のサイズを確かめる
    with zipfile.ZipFile(io.BytesIO(excel_bytes)) as zf:
        uncompressed: int = sum(info.file_size for info in zf.infolist())
    if uncompressed > MAX_UNCOMPRESSED_BYTES:
        raise ValueError(f"展開後のサイズが上限 ({MAX_UNCOMPRESSED_BYTES} バイト) を超えています")

    # read_only で 1 行ずつ読み、読みながらセル数と文字数を確かめる
    wb: Workbook = load_workbook(io.BytesIO(excel_bytes), read_only=True, data_only=True)
    sheets: list[tuple[str, list[list[str]]]] = []
    total_cells: int = 0
    try:
        for ws in wb.worksheets:
            rows: list[list[str]] = []
            for values in ws.iter_rows(values_only=True):
                total_cells += len(values)
                if total_cells > MAX_CELLS:
                    raise ValueError(f"セル数が上限 ({MAX_CELLS}) を超えています")
                row: list[str] = [to_cell_text(v) for v in values]
                for value in row:
                    if len(value) > MAX_CELL_CHARS:
                        raise ValueError(f"シート {ws.title} に {MAX_CELL_CHARS} 文字を超えるセルがあります")
                rows.append(row)
            sheets.append((ws.title, rows))
    finally:
        wb.close()
    return sheets


def mask_sheet(title: str, rows: list[list[str]], usage_total: dict[str, int]) -> tuple[SheetResult, str]:
    """シートをセル単位でマスクし、セル単位の結果とマスク済み TSV を返す。

    セルを 1 つずつ別のコンテンツブロックにして送る。1 つのテキストにまとめると、
    隣り合うセル (氏名とフリガナなど) が 1 つの PII として検出され、セルの区切りが消えるため。
    """
    # (行, 列)。空のセルは送らない
    targets: list[tuple[int, int]] = []
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if not value:
                continue
            targets.append((r, c))

    blocks: list[str] = [rows[r][c] for r, c in targets]
    masked_rows: list[list[str]] = [list(row) for row in rows]
    failed_rows: set[int] = set()
    detections: list[Detection] = []

    for span in chunk_blocks(blocks):
        masked, found = apply_guardrail_blocks([blocks[i] for i in span], "INPUT", usage_total)
        detections.extend(found)
        for k, i in enumerate(span):
            r, c = targets[i]
            if masked is None:
                failed_rows.add(r)
                continue
            masked_rows[r][c] = masked[k]

    result_rows: list[MappedRow | UnmappedRow] = []
    masked_lines: list[str] = []
    for r, (row, masked_row) in enumerate(zip(rows, masked_rows)):
        if r in failed_rows:
            # マスクできたか確かめられない行は、Claude に渡さない
            unmapped: UnmappedRow = {"mapped": False, "original": row, "masked_line": None}
            result_rows.append(unmapped)
            continue
        cells: list[CellResult] = []
        for original, masked_cell in zip(row, masked_row):
            cells.append({"original": original, "masked": masked_cell, "types": find_placeholders(original, masked_cell)})
        mapped: MappedRow = {"mapped": True, "cells": cells}
        result_rows.append(mapped)
        masked_lines.append("\t".join(masked_row))

    sheet: SheetResult = {"name": title, "rows": result_rows, "detections": detections}
    return sheet, "\n".join(masked_lines)


def ask_claude(instruction: str, sheet_texts: list[tuple[str, str]]) -> tuple[str, TokenUsageTypeDef]:
    data: str = "\n\n".join(f'<sheet name="{name}">\n{text}\n</sheet>' for name, text in sheet_texts)
    res: ConverseResponseTypeDef = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": f"{instruction}\n\n<data>\n{data}\n</data>"}]}],
        inferenceConfig={"maxTokens": 2048},
    )

    parts: list[str] = []
    for block in res["output"]["message"]["content"]:
        if "text" in block:
            parts.append(block["text"])
    return "".join(parts), res["usage"]


@app.entrypoint
def invoke(payload: InvokePayload) -> InvokeResult:
    # 入力の確認をすべて終えてから、ApplyGuardrail を呼ぶ
    sheet_rows: list[tuple[str, list[list[str]]]] = read_sheets(base64.b64decode(payload["content_base64"]))
    raw_instruction: str = payload.get("instruction", "")
    if not raw_instruction.strip():
        raw_instruction = DEFAULT_INSTRUCTION
    if len(raw_instruction) > MAX_INSTRUCTION_CHARS:
        raise ValueError(f"指示が上限 ({MAX_INSTRUCTION_CHARS} 文字) を超えています")

    guardrail_usage: dict[str, int] = {}
    sheets: list[SheetResult] = []
    sheet_texts: list[tuple[str, str]] = []
    for title, rows in sheet_rows:
        sheet, masked_text = mask_sheet(title, rows, guardrail_usage)
        sheets.append(sheet)
        sheet_texts.append((title, masked_text))

    instruction, instruction_detections = apply_guardrail(raw_instruction, "INPUT", guardrail_usage)

    answer, model_usage = ask_claude(instruction, sheet_texts)
    answer_masked, answer_detections = apply_guardrail(answer, "OUTPUT", guardrail_usage)

    return {
        "filename": payload["filename"],
        "sheets": sheets,
        "instruction": {"masked": instruction, "detections": instruction_detections},
        "claude": {
            "model_id": MODEL_ID,
            "answer": answer,
            "answer_masked": answer_masked,
            "detections": answer_detections,
            "usage": model_usage,
        },
        "guardrail_usage": guardrail_usage,
    }


if __name__ == "__main__":
    app.run()

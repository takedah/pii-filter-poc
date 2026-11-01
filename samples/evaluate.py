# /// script
# requires-python = ">=3.13"
# ///
"""アプリの結果 JSON を expected.json と突き合わせ、Guardrails の検出状況を集計する。

使い方: uv run samples/evaluate.py <結果 JSON> [expected.json]
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PLACEHOLDER = re.compile(r"\{[A-Z0-9_]+\}")
DIGIT = re.compile(r"[0-9０-９]")


def column_letter(index):
    """0 始まりの列番号を A, B, ..., Z, AA の形にする。"""
    letters = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def cells_of(sheet):
    """結果の 1 シートから {座標: セル} を返す。対応づけに失敗した行は含めない。"""
    cells = {}
    for r, row in enumerate(sheet["rows"]):
        if not row["mapped"]:
            continue
        for c, cell in enumerate(row["cells"]):
            cells[f"{column_letter(c)}{r + 1}"] = cell
    return cells


def number_mask_state(cell):
    """数字の PII について、マスクの状態を 未検出 / 一部残存 / 完全 に分ける。プレースホルダー以外に数字が残っているかで判定する。"""
    if cell["masked"] == cell["original"]:
        return "未検出"
    if DIGIT.search(PLACEHOLDER.sub("", cell["masked"])):
        return "一部残存"
    return "完全"


def main():
    result = json.loads(Path(sys.argv[1]).read_text())
    expected_path = Path(__file__).parent / "expected.json"
    if len(sys.argv) > 2:
        expected_path = Path(sys.argv[2])
    expected = json.loads(expected_path.read_text())

    by_label = defaultdict(lambda: [0, 0])  # 正解ラベル -> [セル数, 検出ありのセル数]
    my_numbers = []
    false_positives = []
    unmapped = 0
    for sheet in result["sheets"]:
        cells = cells_of(sheet)
        unmapped += sum(1 for row in sheet["rows"] if not row["mapped"])
        for coord, labels in expected.get(sheet["name"], {}).items():
            cell = cells.get(coord)
            if cell is None:
                continue
            for label in labels or ["(PII なし)"]:
                by_label[label][0] += 1
                if cell["types"]:
                    by_label[label][1] += 1
            if "MY_NUMBER" in labels:
                my_numbers.append((sheet["name"], coord, cell, number_mask_state(cell)))
            elif "JP_MYNUMBER" in cell["types"]:
                false_positives.append((sheet["name"], coord, labels, cell))

    print("## 正解ラベルごとの検出状況\n")
    print("| 正解ラベル | セル数 | 検出あり | 検出率 |")
    print("|---|---:|---:|---:|")
    for label, (total, detected) in sorted(by_label.items()):
        print(f"| {label} | {total} | {detected} | {detected / total:.0%} |")

    print("\n## マイナンバーのセル\n")
    states = Counter(state for *_, state in my_numbers)
    print(" / ".join(f"{state}: {states[state]}" for state in ["完全", "一部残存", "未検出"]) + "\n")
    print("| シート | セル | 元の値 | マスク後 | 判定 |")
    print("|---|---|---|---|---|")
    for name, coord, cell, state in my_numbers:
        print(f"| {name} | {coord} | {cell['original']} | {cell['masked']} | {state} |")

    print("\n## マイナンバー以外で JP_MYNUMBER が付いたセル (誤検出)\n")
    print("| シート | セル | 正解ラベル | 元の値 | マスク後 |")
    print("|---|---|---|---|---|")
    for name, coord, labels, cell in false_positives:
        print(f"| {name} | {coord} | {', '.join(labels) or '(PII なし)'} | {cell['original']} | {cell['masked']} |")

    print(f"\n対応づけに失敗した行: {unmapped}")


if __name__ == "__main__":
    main()

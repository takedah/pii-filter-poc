# /// script
# requires-python = ">=3.13"
# dependencies = ["openpyxl"]
# ///
"""PII 検証用のテスト Excel と正解ラベル (expected.json) を生成する。

すべて架空のデータ。メールは example.jp / example.com、
カード番号はテスト用番号、電話番号は架空の番号を使う。
"""
import json
import random
from pathlib import Path

from openpyxl import Workbook

OUT_DIR = Path(__file__).parent
random.seed(42)

JA_LAST = [("山田", "ヤマダ"), ("佐藤", "サトウ"), ("鈴木", "スズキ"), ("高橋", "タカハシ"), ("田中", "タナカ"),
           ("伊藤", "イトウ"), ("渡辺", "ワタナベ"), ("中村", "ナカムラ"), ("小林", "コバヤシ"), ("加藤", "カトウ")]
JA_FIRST = [("太郎", "タロウ"), ("花子", "ハナコ"), ("一郎", "イチロウ"), ("美咲", "ミサキ"), ("健太", "ケンタ"),
            ("陽菜", "ヒナ"), ("翔太", "ショウタ"), ("結衣", "ユイ"), ("大輔", "ダイスケ"), ("さくら", "サクラ")]
# 町名を「架空町」にして、実在する住所と一致しないようにする
JA_ADDR = ["東京都千代田区架空町{}-{}-{}", "大阪府大阪市北区架空町{}-{}-{}", "愛知県名古屋市中区架空町{}-{}-{}",
           "福岡県福岡市博多区架空町{}-{}-{}", "北海道札幌市中央区架空町{}-{}-{}"]
EN_NAMES = ["John Smith", "Emily Johnson", "Michael Brown", "Sarah Davis", "David Wilson",
            "Jessica Taylor", "James Anderson", "Ashley Thomas", "Robert Martin", "Laura White"]
TEST_CARDS = ["4111 1111 1111 1111", "5555-5555-5555-4444", "378282246310005", "6011111111111117"]


def digits(n):
    return "".join(random.choice("0123456789") for _ in range(n))


def ja_row(i):
    """(見出し, 値, 正解ラベル) のリストを返す。表記ゆれは i で切り替える。"""
    (last, last_kana), (first, first_kana) = random.choice(JA_LAST), random.choice(JA_FIRST)
    sep = " " if i % 2 else ""  # 姓名の間の空白あり/なし
    # 携帯(ハイフンあり) / 固定(ハイフンなし)。実在する番号と一致しにくいよう、ひと目で架空とわかる番号にする
    phone = f"090-0000-{i:04d}" if i % 3 else f"030000{i:04d}"
    postal = f"〒{digits(3)}-{digits(4)}" if i % 2 else f"{digits(3)}-{digits(4)}"
    n = my_number_digits()
    my_number = f"{n[:4]} {n[4:8]} {n[8:]}" if i % 2 else n
    other = random.choice(JA_LAST)[0]
    staff_email = f"staff{i:03d}@example.jp"
    remarks = [
        ("特記事項なし", []),
        (f"{last}様より電話あり。折り返しは {phone} まで", ["NAME", "PHONE"]),
        (f"担当: {other}（{staff_email}）", ["NAME", "EMAIL"]),
        ("田中工業株式会社との取引あり", []),  # 社名の誤検出チェック
    ][i % 4]
    return [
        ("氏名", f"{last}{sep}{first}", ["NAME"]),
        ("フリガナ", f"{last_kana}{sep}{first_kana}", ["NAME"]),
        ("年齢", random.randint(20, 79), ["AGE"]),
        ("メールアドレス", f"user{i:03d}@example.jp", ["EMAIL"]),
        ("電話番号", phone, ["PHONE"]),
        ("郵便番号", postal, ["POSTAL_CODE"]),
        ("住所", random.choice(JA_ADDR).format(random.randint(1, 9), random.randint(1, 20), random.randint(1, 30)),
         ["ADDRESS"]),
        ("マイナンバー", my_number, ["MY_NUMBER"]),
        ("クレジットカード", random.choice(TEST_CARDS), ["CARD_NUMBER"]),
        ("備考", *remarks),
    ]


def en_row(i):
    name = EN_NAMES[i]
    notes = [
        ("No remarks", []),
        (f"Call back {name.split()[0]} at +1-202-555-01{i:02d}", ["NAME", "PHONE"]),
    ][i % 2]
    return [
        ("Name", name, ["NAME"]),
        ("Age", random.randint(20, 79), ["AGE"]),
        ("Email", f"{name.split()[0].lower()}@example.com", ["EMAIL"]),
        ("Phone", f"+1-202-555-01{i:02d}", ["PHONE"]),
        ("Address", f"{random.randint(100, 999)} Example St, Anytown, IL 62701", ["ADDRESS"]),
        ("Card", random.choice(TEST_CARDS), ["CARD_NUMBER"]),
        ("Notes", *notes),
    ]


def my_number_digits():
    """マイナンバーの形をした 12 桁の番号を返す。

    実在する番号と偶然一致しないよう、チェックデジットはわざと誤った値にする
    (発行される番号はチェックデジットが必ず正しい)。
    """
    base = digits(11)
    # P は右から n 番目の数字、Q は n <= 6 なら n + 1、それ以外は n - 5
    total = sum(int(p) * (n + 1 if n <= 6 else n - 5) for n, p in enumerate(reversed(base), start=1))
    remainder = total % 11
    check = 0 if remainder <= 1 else 11 - remainder
    return f"{base}{(check + 1) % 10}"


def to_fullwidth(text):
    return text.translate(str.maketrans("0123456789 -", "０１２３４５６７８９　－"))


def my_number_cases(round_):
    """(ケース名, 値, 正解ラベル) のリストを返す。マイナンバーの表記ゆれと、マイナンバーではない似た数字を含む。"""
    n = my_number_digits()
    spaced = f"{n[:4]} {n[4:8]} {n[8:]}"
    hyphen = f"{n[:4]}-{n[4:8]}-{n[8:]}"
    return [
        ("区切りなし", n, ["MY_NUMBER"]),
        ("空白区切り", spaced, ["MY_NUMBER"]),
        ("ハイフン区切り", hyphen, ["MY_NUMBER"]),
        ("全角数字", to_fullwidth(n), ["MY_NUMBER"]),
        ("全角数字・全角ハイフン区切り", to_fullwidth(hyphen), ["MY_NUMBER"]),
        ("文中", f"マイナンバーは{n}です", ["MY_NUMBER"]),
        ("ラベル付き", f"個人番号: {spaced}", ["MY_NUMBER"]),
        ("2 件を含む", f"本人 {n} / 配偶者 {my_number_digits()}", ["MY_NUMBER"]),
        ("11 桁の数字", digits(11), []),
        ("13 桁の数字 (法人番号など)", digits(13), []),
        ("12 桁の注文番号", f"注文番号 {digits(12)}", []),
        ("12 桁の日時", f"2026110{round_ + 1}1230", []),
        ("携帯電話番号", f"090-0000-{9000 + round_:04d}", ["PHONE"]),
        ("クレジットカード番号", random.choice(TEST_CARDS), ["CARD_NUMBER"]),
    ]


def my_number_rows():
    rows = []
    for round_ in range(2):
        for case, value, labels in my_number_cases(round_):
            rows.append([("ケース", case, []), ("値", value, labels)])
    return rows


def write_sheet(ws, rows, expected):
    for col, (header, _, _) in enumerate(rows[0], start=1):
        ws.cell(row=1, column=col, value=header)
    for r, row in enumerate(rows, start=2):
        for col, (_, value, labels) in enumerate(row, start=1):
            cell = ws.cell(row=r, column=col, value=value)
            expected[cell.coordinate] = labels


def main():
    wb = Workbook()
    expected = {}
    sheets = [("顧客一覧", [ja_row(i) for i in range(20)]), ("English", [en_row(i) for i in range(10)]),
              ("マイナンバー", my_number_rows())]
    for idx, (title, rows) in enumerate(sheets):
        ws = wb.active if idx == 0 else wb.create_sheet()
        ws.title = title
        expected[title] = {}
        write_sheet(ws, rows, expected[title])
    wb.save(OUT_DIR / "test_pii.xlsx")
    (OUT_DIR / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

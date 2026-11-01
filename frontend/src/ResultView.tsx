import type { CellResult, Detection, InvokeResult, MappedRow, SheetResult, UnmappedRow } from "./types";

function countTypes(sheets: SheetResult[]): Map<string, number> {
  const counts: Map<string, number> = new Map();
  for (const sheet of sheets) {
    for (const row of sheet.rows) {
      if (!row.mapped) {
        continue;
      }
      for (const cell of row.cells) {
        // 1 つのセルに同じ種類が複数あっても、セル数としては 1 回だけ数える
        for (const type of new Set(cell.types)) {
          counts.set(type, (counts.get(type) ?? 0) + 1);
        }
      }
    }
  }
  return counts;
}

function columnCount(sheet: SheetResult): number {
  let count: number = 1;
  for (const row of sheet.rows) {
    if (row.mapped) {
      count = Math.max(count, row.cells.length);
    } else {
      count = Math.max(count, row.original.length);
    }
  }
  return count;
}

function downloadJson(result: InvokeResult): void {
  const blob: Blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
  const url: string = URL.createObjectURL(blob);
  const link: HTMLAnchorElement = document.createElement("a");
  link.href = url;
  link.download = result.filename.replace(/\.xlsx$/, "") + "_result.json";
  link.click();
  URL.revokeObjectURL(url);
}

export function ResultView({ result }: { result: InvokeResult }) {
  const counts: Map<string, number> = countTypes(result.sheets);
  return (
    <>
      <section className="card">
        <h2>サマリー</h2>
        <button type="button" onClick={() => downloadJson(result)}>結果を JSON でダウンロード</button>
        <h3>検出されたセル数（種類別）</h3>
        <KeyValueTable entries={[...counts.entries()]} emptyText="検出なし" />
        <h3>Guardrails の消費量（text units）</h3>
        <KeyValueTable entries={Object.entries(result.guardrail_usage)} emptyText="なし" />
        <h3>Claude のトークン数（{result.claude.model_id}）</h3>
        <KeyValueTable
          entries={[
            ["inputTokens", result.claude.usage.inputTokens],
            ["outputTokens", result.claude.usage.outputTokens],
          ]}
          emptyText="なし"
        />
      </section>

      <section className="card">
        <h2>Claude の応答</h2>
        <p className="instruction">指示（マスク後）: {result.instruction.masked}</p>
        <pre className="answer">{result.claude.answer}</pre>
        <h3>応答チェック（ApplyGuardrail OUTPUT）</h3>
        <AnswerCheck masked={result.claude.answer_masked} detections={result.claude.detections} />
      </section>

      {result.sheets.map((sheet) => (
        <SheetTable key={sheet.name} sheet={sheet} />
      ))}
    </>
  );
}

function KeyValueTable({ entries, emptyText }: { entries: [string, number][]; emptyText: string }) {
  if (entries.length === 0) {
    return <p>{emptyText}</p>;
  }
  return (
    <table className="kv">
      <tbody>
        {entries.map(([key, value]) => (
          <tr key={key}>
            <th>{key}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AnswerCheck({ masked, detections }: { masked: string; detections: Detection[] }) {
  if (detections.length === 0) {
    return <p>応答から PII は検出されませんでした。</p>;
  }
  return (
    <>
      <p className="error">応答から PII が検出されました。マスク後の応答:</p>
      <pre className="answer">{masked}</pre>
      <ul>
        {detections.map((d, i) => (
          <li key={i}>{d.filter} / {d.type}: {d.match}</li>
        ))}
      </ul>
    </>
  );
}

function SheetTable({ sheet }: { sheet: SheetResult }) {
  const columns: number = columnCount(sheet);
  return (
    <section className="card">
      <h2>シート: {sheet.name}</h2>
      <p>色付きのセルは検出されたセルです（上段がマスク後、下段が元の値）。</p>
      <div className="table-wrap">
        <table className="sheet">
          <tbody>
            {sheet.rows.map((row, i) => (
              <Row key={i} row={row} columns={columns} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Row({ row, columns }: { row: MappedRow | UnmappedRow; columns: number }) {
  if (row.mapped) {
    return (
      <tr>
        {row.cells.map((cell, i) => (
          <Cell key={i} cell={cell} />
        ))}
      </tr>
    );
  }
  let text: string = "（ApplyGuardrail の結果をセルに対応づけられなかったため、この行は Claude に渡していません）";
  if (row.masked_line !== null) {
    text = row.masked_line;
  }
  return (
    <tr className="unmapped">
      <td colSpan={columns}>対応づけ失敗: {text}</td>
    </tr>
  );
}

function Cell({ cell }: { cell: CellResult }) {
  if (cell.types.length === 0) {
    return <td>{cell.original}</td>;
  }
  return (
    <td className="detected" title={cell.types.join(", ")}>
      <div className="masked">{cell.masked}</div>
      <div className="original">{cell.original}</div>
    </td>
  );
}

import { useState, type ChangeEvent, type FormEvent } from "react";

import { fileToBase64, invokeAgent } from "./api";
import { ErrorMessage } from "./ErrorMessage";
import { ResultView } from "./ResultView";
import type { InvokeResult } from "./types";

const DEFAULT_INSTRUCTION: string = "このデータの傾向を要約してください。";

export function Analyzer() {
  const [file, setFile] = useState<File | null>(null);
  const [instruction, setInstruction] = useState<string>(DEFAULT_INSTRUCTION);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InvokeResult | null>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const files: FileList | null = event.target.files;
    if (files === null || files.length === 0) {
      setFile(null);
      return;
    }
    setFile(files[0]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (file === null) {
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const contentBase64: string = await fileToBase64(file);
      setResult(await invokeAgent({ filename: file.name, content_base64: contentBase64, instruction }));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  let buttonLabel: string = "実行";
  if (loading) {
    buttonLabel = "処理中...";
  }

  return (
    <>
      <form className="card" onSubmit={handleSubmit}>
        <label>
          Excel ファイル (.xlsx)
          <input type="file" accept=".xlsx" onChange={handleFileChange} required />
        </label>
        <label>
          Claude への指示
          <textarea rows={3} value={instruction} onChange={(e) => setInstruction(e.target.value)} />
        </label>
        <button type="submit" disabled={file === null || loading}>{buttonLabel}</button>
        <ErrorMessage error={error} />
      </form>
      <ResultSection result={result} />
    </>
  );
}

function ResultSection({ result }: { result: InvokeResult | null }) {
  if (result === null) {
    return null;
  }
  return <ResultView result={result} />;
}

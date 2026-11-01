import { fetchAuthSession, type AuthSession } from "aws-amplify/auth";

import type { InvokePayload, InvokeResult } from "./types";

const RUNTIME_ARN: string = import.meta.env.VITE_AGENT_RUNTIME_ARN;

function newSessionId(): string {
  // AgentCore Runtime のセッション ID は 33 文字以上が必要
  return `${crypto.randomUUID()}-${Date.now()}`;
}

export async function fileToBase64(file: File): Promise<string> {
  const bytes: Uint8Array = new Uint8Array(await file.arrayBuffer());
  let binary: string = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

export async function invokeAgent(payload: InvokePayload): Promise<InvokeResult> {
  const session: AuthSession = await fetchAuthSession();
  const accessToken: string | undefined = session.tokens?.accessToken.toString();
  if (accessToken === undefined) {
    throw new Error("ログインしていません");
  }

  const url: string = `/runtimes/${encodeURIComponent(RUNTIME_ARN)}/invocations?qualifier=DEFAULT`;
  const res: Response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
      "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": newSessionId(),
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body: string = await res.text();
    throw new Error(`AgentCore Runtime の呼び出しに失敗しました (${res.status}): ${body}`);
  }
  return (await res.json()) as InvokeResult;
}

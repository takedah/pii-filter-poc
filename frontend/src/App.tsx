import { getCurrentUser, signInWithRedirect, signOut } from "aws-amplify/auth";
import { Hub } from "aws-amplify/utils";
import { useEffect, useState } from "react";

import { Analyzer } from "./Analyzer";
import { ErrorMessage } from "./ErrorMessage";

type AuthState = "checking" | "signedOut" | "signedIn";

export function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // マネージドログインから戻ってきたとき、トークンの取得が終わった時点で通知される
    const unsubscribe: () => void = Hub.listen("auth", ({ payload }) => {
      if (payload.event === "signInWithRedirect") {
        setAuthState("signedIn");
      }
      if (payload.event === "signInWithRedirect_failure") {
        setError("ログインに失敗しました");
        setAuthState("signedOut");
      }
    });
    getCurrentUser()
      .then(() => setAuthState("signedIn"))
      .catch(() => setAuthState("signedOut"));
    return unsubscribe;
  }, []);

  if (authState === "checking") {
    return <main><p>読み込み中...</p></main>;
  }
  if (authState === "signedOut") {
    return (
      <main>
        <h1>PII Filter PoC</h1>
        <button type="button" onClick={() => signInWithRedirect()}>ログイン</button>
        <ErrorMessage error={error} />
      </main>
    );
  }
  return (
    <main>
      <header>
        <h1>PII Filter PoC</h1>
        <button type="button" onClick={() => signOut()}>ログアウト</button>
      </header>
      <Analyzer />
    </main>
  );
}

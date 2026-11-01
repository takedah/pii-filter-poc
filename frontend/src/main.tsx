import { Amplify } from "aws-amplify";
import "aws-amplify/auth/enable-oauth-listener";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./App.css";

// 開発（localhost:5173）と本番（CloudFront）のどちらでも、開いているオリジンに戻ってくる
const redirectUrl: string = `${window.location.origin}/`;

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID,
      loginWith: {
        oauth: {
          domain: import.meta.env.VITE_COGNITO_DOMAIN,
          scopes: ["openid", "email"],
          redirectSignIn: [redirectUrl],
          redirectSignOut: [redirectUrl],
          responseType: "code",
        },
      },
    },
  },
});

const root: HTMLElement | null = document.getElementById("root");
if (root === null) {
  throw new Error("#root が見つかりません");
}
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

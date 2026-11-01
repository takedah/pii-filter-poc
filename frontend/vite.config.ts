import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // 開発中は AgentCore Runtime への呼び出しを dev server 経由で転送する（本番では CloudFront が同じ役割を担う）
    proxy: {
      "/runtimes": {
        target: "https://bedrock-agentcore.ap-northeast-1.amazonaws.com",
        changeOrigin: true,
      },
    },
  },
});

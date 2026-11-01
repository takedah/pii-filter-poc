# pii-filter-poc

Amazon Bedrock Guardrails で、日本のマイナンバーをどこまでマスクできるかを検証した PoC です。

Excel ファイルをアップロードすると、各セルを Guardrails（ApplyGuardrail API）でマスクしてから、マスクしたデータだけを Claude（Amazon Bedrock の jp. 推論プロファイル）に渡して分析させます。Claude の応答も、もう一度 Guardrails でチェックします。

マスクの対象は、セルの値と Claude への指示だけです。シート名はマスクせずに、そのまま Claude に渡します。

マイナンバーは、Guardrails の機密情報フィルターに登録した正規表現で検出します。組み込みの PII フィルター（氏名、住所、年齢、メールアドレス、電話番号、クレジットカード番号）と、日本の電話番号・郵便番号の正規表現も、参考として検証しています。

> テストデータはすべて架空の値です。実在する個人の情報は含まれていません。

## 構成

```
ブラウザ ── CloudFront ─┬─ S3（React アプリ）
                         └─ /runtimes/* ── AgentCore Runtime（東京）
                                              ├─ ApplyGuardrail（INPUT / OUTPUT）
                                              └─ Converse（Claude Haiku 4.5、jp. 推論プロファイル）
認証：Amazon Cognito（マネージドログイン）＋ AgentCore Runtime の JWT 認証
```

## ディレクトリ

| パス | 内容 |
|---|---|
| `PiiFilterPoc/` | AgentCore CLI のプロジェクト |
| `PiiFilterPoc/app/PiiFilterPoc/main.py` | Runtime のコード（マスクと Claude の呼び出し） |
| `PiiFilterPoc/agentcore/agentcore.example.json` | Runtime の設定の例 |
| `frontend/` | フロントエンド（React + Vite + Amplify） |
| `samples/generate_test_excel.py` | テストデータ（`test_pii.xlsx`）と正解ラベル（`expected.json`）の生成 |
| `samples/evaluate.py` | 結果の JSON と正解ラベルの突き合わせ |

## 使い方

前提：Node.js 20 以上、[AgentCore CLI](https://www.npmjs.com/package/@aws/agentcore)、uv、Python 3.13

事前に、マネジメントコンソールで次のものを作成しておきます。

- Bedrock Guardrails（機密情報フィルター。正規表現は下を参照）
- Runtime の実行ロール（Guardrail への `bedrock:ApplyGuardrail` と、jp. 推論プロファイル経由の `bedrock:InvokeModel`）
- Cognito のユーザープールと、シークレットのないアプリクライアント

### Runtime

```bash
cd PiiFilterPoc
cp agentcore/agentcore.example.json agentcore/agentcore.json
# agentcore.json の <GUARDRAIL_ID>、<ACCOUNT_ID>、<EXECUTION_ROLE_NAME>、<USER_POOL_ID>、<CLIENT_ID> を書き換える
agentcore deploy --region ap-northeast-1
```

### フロントエンド

`frontend/.env.local` を作成します。

```
VITE_USER_POOL_ID=<ユーザープール ID>
VITE_USER_POOL_CLIENT_ID=<アプリクライアント ID>
VITE_COGNITO_DOMAIN=<Cognito のドメイン（https:// は付けない）>
VITE_AGENT_RUNTIME_ARN=<Runtime の ARN>
```

```bash
cd frontend
npm install
npm run dev     # ローカルで動かす（http://localhost:5173/）
npm run build   # S3 に置くファイルを dist/ に作る
```

公開するときは、CloudFront の `/runtimes/*` を `bedrock-agentcore.ap-northeast-1.amazonaws.com` に振り分けます（キャッシュは CachingDisabled、オリジンリクエストポリシーは AllViewerExceptHostHeader）。

### テストデータと集計

```bash
uv run samples/generate_test_excel.py
# アプリで samples/test_pii.xlsx を処理し、結果の JSON をダウンロードする
uv run samples/evaluate.py samples/test_pii_result.json
```

## Guardrails の正規表現

`JP_MYNUMBER`（半角 12 桁のマイナンバー）

```
\b\d{4}[- ]?\d{4}[- ]?\d{4}\b
```

`JP_MYNUMBER_FULLWIDTH`（全角 12 桁のマイナンバー）

```
[０-９]{4}[－　 ]?[０-９]{4}[－　 ]?[０-９]{4}
```

`JP_PHONE`（日本の電話番号）

```
(?:\+81[- ]?|\b0)(?:[5789]0-?\d{4}-?\d{4}|\d{1,4}-\d{1,4}-\d{4}|120-?\d{3}-?\d{3}|\d{9})\b
```

`JP_POSTAL_CODE`（郵便番号）

```
〒 ?\d{3}-?\d{4}\b|\b\d{3}-\d{4}\b
```

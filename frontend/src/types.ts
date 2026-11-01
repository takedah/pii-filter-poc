// agent/main.py の TypedDict と同じ形

export type InvokePayload = {
  filename: string;
  content_base64: string;
  instruction?: string;
};

export type Detection = {
  filter: "PII" | "REGEX";
  type: string;
  match: string;
  action: string;
};

export type CellResult = {
  original: string;
  masked: string;
  types: string[];
};

export type MappedRow = {
  mapped: true;
  cells: CellResult[];
};

export type UnmappedRow = {
  mapped: false;
  original: string[];
  masked_line: string | null;
};

export type SheetResult = {
  name: string;
  rows: (MappedRow | UnmappedRow)[];
  detections: Detection[];
};

export type TokenUsage = {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
};

export type InvokeResult = {
  filename: string;
  sheets: SheetResult[];
  instruction: {
    masked: string;
    detections: Detection[];
  };
  claude: {
    model_id: string;
    answer: string;
    answer_masked: string;
    detections: Detection[];
    usage: TokenUsage;
  };
  guardrail_usage: Record<string, number>;
};

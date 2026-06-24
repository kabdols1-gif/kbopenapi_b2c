"use client";

import { useEffect, useMemo, useState } from "react";
import kbCatalog from "./samples.generated.json";
import OpenApiTestClient, {
  type OpenApiFieldSpec,
  type OpenApiSample,
  type OpenApiTokenProcedure,
} from "@/components/openapi/OpenApiTestClient";

const FALLBACK_BASE_URL =
  process.env.NEXT_PUBLIC_OPENAPI_TEST_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8020";

const BUILD_RUNTIME_MODE = normalizeRuntimeMode(process.env.NEXT_PUBLIC_OPENAPI_MODE);

type ApiMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type RuntimeMode = "development" | "production";

type CatalogSample = {
  id: string;
  label: string;
  method: ApiMethod;
  endpoint?: string;
  path?: string;
  transactionCode?: string;
  businessCategory?: OpenApiSample["businessCategory"];
  description: string;
  headers?: Record<string, string>;
  query?: Record<string, unknown>;
  body?: Record<string, unknown>;
  inputSpec?: OpenApiFieldSpec[];
  outputSpec?: OpenApiFieldSpec[];
};

type KbCatalog = {
  b2c?: CatalogSample[];
};

const DEFAULT_ENVIRONMENTS: Record<RuntimeMode, { kbB2cBaseUrl: string; kbB2cTokenBaseUrl: string }> = {
  development: {
    kbB2cBaseUrl: process.env.NEXT_PUBLIC_OPENAPI_DEV_KB_B2C_BASE_URL || "https://ddeveloper.kbsec.com:32484",
    kbB2cTokenBaseUrl:
      process.env.NEXT_PUBLIC_OPENAPI_DEV_KB_B2C_TOKEN_BASE_URL || "https://ddeveloper.kbsec.com:32484",
  },
  production: {
    kbB2cBaseUrl: process.env.NEXT_PUBLIC_OPENAPI_PROD_KB_B2C_BASE_URL || "https://developer.kbsec.com:32484",
    kbB2cTokenBaseUrl:
      process.env.NEXT_PUBLIC_OPENAPI_PROD_KB_B2C_TOKEN_BASE_URL || "https://developer.kbsec.com:32484",
  },
};

function normalizeRuntimeMode(raw: string | undefined | null): RuntimeMode {
  const normalized = (raw || "").trim().toLowerCase();
  return ["prod", "production", "real", "live"].includes(normalized) ? "production" : "development";
}

function toKbServicePath(entry: CatalogSample) {
  if (entry.path) return entry.path;
  if (entry.endpoint) return entry.endpoint;

  const transactionCode = (entry.transactionCode || entry.id)
    .replace(/^Tkb_/i, "")
    .replace(/_B2C$/i, "")
    .toLowerCase();
  return `/api/v1/${transactionCode}`;
}

function toOpenApiSample(entry: CatalogSample, baseUrl: string): OpenApiSample {
  return {
    id: entry.id,
    label: entry.label,
    method: entry.method,
    path: toKbServicePath(entry),
    description: entry.description,
    businessCategory: entry.businessCategory,
    headers: {
      "Content-Type": "application/json",
      appKey: "{{clientId}}",
      Authorization: "bearer {{access_token}}",
      ...(entry.headers ?? {}),
    },
    query: entry.query,
    body: entry.body,
    baseUrl,
    source: "trx-rule",
    inputSpec: entry.inputSpec,
    outputSpec: entry.outputSpec,
  };
}

function tokenProcedureForMode(mode: RuntimeMode): OpenApiTokenProcedure {
  const env = DEFAULT_ENVIRONMENTS[mode];
  return {
    id: "kb-b2c-token",
    label: "KB B2C 토큰 발급(OAuth2)",
    mode: "B2C",
    environment: env.kbB2cTokenBaseUrl,
    steps: [
      `1) POST ${env.kbB2cTokenBaseUrl}/oauth2/token 으로 clientId/clientSecret 및 grantType=client_credentials를 전달합니다.`,
      "2) 응답의 access_token을 샘플 API 요청 Authorization 헤더에 사용합니다.",
    ],
    recommendedHeaders: [
      "Authorization: bearer <access_token>",
      "appKey: <clientId>",
      "Content-Type: application/json",
    ],
  };
}

export default function OpenApiTestPage() {
  const [runtimeMode, setRuntimeMode] = useState<RuntimeMode>(BUILD_RUNTIME_MODE);

  useEffect(() => {
    if (BUILD_RUNTIME_MODE === "production") return;
    try {
      const cached = window.localStorage.getItem("kb.openapi.runtimeMode");
      if (cached) setRuntimeMode(normalizeRuntimeMode(cached));
    } catch {
      // Runtime mode persistence is optional.
    }
  }, []);

  function selectRuntimeMode(mode: RuntimeMode) {
    setRuntimeMode(mode);
    try {
      window.localStorage.setItem("kb.openapi.runtimeMode", mode);
    } catch {
      // Runtime mode persistence is optional.
    }
  }

  const defaultBaseUrl = DEFAULT_ENVIRONMENTS[runtimeMode].kbB2cBaseUrl || FALLBACK_BASE_URL;
  const samples = useMemo(
    () => ((kbCatalog as KbCatalog).b2c ?? []).map((entry) => toOpenApiSample(entry, defaultBaseUrl)),
    [defaultBaseUrl]
  );
  const tokenProcedures = useMemo(() => [tokenProcedureForMode(runtimeMode)], [runtimeMode]);

  return (
    <OpenApiTestClient
      headerContent={
        <div className="flex flex-wrap items-center justify-between gap-4 border-b-4 border-[#fcb514] pb-4">
          <div className="flex min-w-0 items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-[#fcb514] text-lg font-black text-[#2c2a26]">
              KB
            </div>
            <div className="min-w-0">
              <p className="text-sm font-black text-[#8a6400]">KB OpenAPI</p>
              <h1 className="text-2xl font-black tracking-normal text-[#2c2a26]">KB 전용 OpenAPI 테스트</h1>
              <p className="mt-1 text-sm font-semibold text-slate-500">KB증권 B2C API 연동 테스트</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-black">
            <span className="rounded-full bg-[#fff4cc] px-3 py-1 text-[#7a5500]">B2C {samples.length}건</span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">{runtimeMode}</span>
          </div>
        </div>
      }
      modeSelectorContent={
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#e3d8bd] bg-[#fffaf0] px-3 py-2">
          <span className="text-xs font-black text-[#6b5b3f]">환경</span>
          {(["development", "production"] as RuntimeMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => selectRuntimeMode(mode)}
              className={`rounded-md border px-3 py-1.5 text-xs font-black transition ${
                runtimeMode === mode
                  ? "border-[#2c2a26] bg-[#2c2a26] text-white"
                  : "border-[#d7cfbf] bg-white text-[#2c2a26] hover:bg-[#fff4cc]"
              }`}
            >
              {mode === "production" ? "운영" : "개발"}
            </button>
          ))}
        </div>
      }
      runtimeMode={runtimeMode}
      samples={samples}
      historyStorageKey="kb.openapi.sample.history"
      defaultBaseUrl={defaultBaseUrl}
      broker="Tkb"
      credentialStorageKey="kb.openapi.sample.credentials"
      tokenProcedures={tokenProcedures}
    />
  );
}

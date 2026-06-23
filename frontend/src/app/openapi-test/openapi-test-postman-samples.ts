import type { OpenApiSample } from "@/components/openapi/OpenApiTestClient";

const IS_OPENAPI_PRODUCTION_MODE = ["production", "prod"].includes(
  (process.env.NEXT_PUBLIC_OPENAPI_MODE || "development").toLowerCase()
);
const KB_B2C_POSTMAN_BASE_URL = IS_OPENAPI_PRODUCTION_MODE
  ? process.env.NEXT_PUBLIC_OPENAPI_PROD_KB_B2C_TOKEN_BASE_URL || "https://developer.kbsec.com"
  : process.env.NEXT_PUBLIC_OPENAPI_DEV_KB_B2C_TOKEN_BASE_URL || "https://ddeveloper.kbsec.com:32484";

export const POSTMAN_B2C_SEED_SAMPLES: OpenApiSample[] = [
  {
    id: "postman-apps",
    label: "포스트맨-1: /service/apps",
    method: "POST",
    path: "/service/apps",
    baseUrl: KB_B2C_POSTMAN_BASE_URL,
    description: "사용자 인증 정보를 포함한 B2C 앱 등록 요청 샘플입니다.",
    headers: {
      "Content-Type": "application/json",
    },
    body: {
      dataHeader: {
        udId: "UDID",
        subChannel: "subChannel",
        deviceModel: "Android",
        deviceOs: "Android",
        carrier: "KT",
        connectionType: "..",
        appName: "..",
        appVersion: "..",
        scrNo: "0000",
      },
      dataBody: {
        hndlCcd: "APP_REG",
        tloginId: "test-user-01",
        accountNo: "0000000000",
        cellPhone: "010-0000-0000",
        email: "test@example.com",
      },
    },
  },
  {
    id: "postman-token",
    label: "포스트맨-2: OAuth2 토큰",
    method: "POST",
    path: "/oauth2/token",
    baseUrl: KB_B2C_POSTMAN_BASE_URL,
    description: "client_credentials 방식의 토큰 발급 테스트입니다.",
    headers: {
      "Content-Type": "application/json",
    },
    body: {
      dataHeader: {
        messageId: "demo-message-id",
      },
      dataBody: {
        grantType: "client_credentials",
        clientId: "sample-client-id",
        clientSecret: "sample-client-secret",
      },
    },
  },
  {
    id: "postman-api",
    label: "포스트맨-3: /api/v1/ssam1802",
    method: "POST",
    path: "/api/v1/ssam1802",
    baseUrl: KB_B2C_POSTMAN_BASE_URL,
    description: "B2C 서비스 API 예제입니다.",
    headers: {
      "Content-Type": "application/json",
      appKey: "demo-app-key",
      Authorization: "Bearer {{access_token}}",
    },
    body: {
      dataHeader: {
        messageId: "demo-message-id",
      },
      dataBody: {
        pFinPrdSeqNo: "1",
        ctn: "00000000",
      },
    },
  },
];

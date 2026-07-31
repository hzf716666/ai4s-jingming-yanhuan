/**
 * Type declarations for @qoder-ai/qoder-agent-sdk
 * This is an optional dependency - the module may not be installed.
 * These declarations allow TypeScript to compile without errors.
 */

declare module "@qoder-ai/qoder-agent-sdk" {
  export interface QoderSDK {
    query: (options: any) => AsyncIterable<any>;
    qodercliAuth: () => any;
    accessTokenFromEnv: () => any;
    QoderAgentOptions: any;
  }

  export const query: QoderSDK["query"];
  export const qodercliAuth: QoderSDK["qodercliAuth"];
  export const accessTokenFromEnv: QoderSDK["accessTokenFromEnv"];
}

/// <reference types="vite/client" />

declare const __BIOMATCAD_DEMO_MODE__: boolean;

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

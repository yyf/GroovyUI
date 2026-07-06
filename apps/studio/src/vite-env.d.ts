/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GROOVY_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

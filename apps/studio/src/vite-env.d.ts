/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GROOVY_API?: string;
  /** owner/repo for model-request issue deep links (default yyf/GroovyUI). */
  readonly VITE_GROOVY_GITHUB_REPO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

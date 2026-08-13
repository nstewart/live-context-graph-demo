/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  /** Zero cache WebSocket/HTTP endpoint (docker-compose sets this). */
  readonly VITE_ZERO_URL?: string
  /** LangGraph agent service (docker-compose sets this; agent profile only). */
  readonly VITE_AGENT_URL?: string
  /** Materialize console, for the "Open SQL Shell" link. Defaults to the
   *  emulator's console port when unset (see docker-compose MZ_CONSOLE_PORT). */
  readonly VITE_MZ_CONSOLE_URL?: string
  /** Active white-label skin. Display only -- the label's content comes from
   *  src/generated/label.json. See docs/WHITE_LABELING.md. */
  readonly VITE_DEMO_LABEL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  /** Materialize console, for the "Open SQL Shell" link. Defaults to the
   *  emulator's console port when unset (see docker-compose MZ_CONSOLE_PORT). */
  readonly VITE_MZ_CONSOLE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

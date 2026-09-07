// Layer: Config. Imports: nothing else in src/. The only module that reads
// import.meta.env -- every other layer receives these values by import.

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

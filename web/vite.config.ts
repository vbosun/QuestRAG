import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPrefixes = [
  "auth",
  "chat",
  "documents",
  "evaluations",
  "permissions",
  "public-services",
  "system",
];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      [`^/(${backendPrefixes.join("|")})(/|$)`]: "http://127.0.0.1:8010",
    }
  }
});

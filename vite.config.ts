import { existsSync, readFileSync } from "node:fs";
import vinext from "vinext";
import { defineConfig, type Plugin } from "vite";
import { createGateway } from "./scripts/value-ui-gateway.mjs";

// Local development uses the same gateway as production (P0-1): the browser
// calls /api on the dev origin; the gateway checks Host (the dev port is read
// per request, so Vite moving from 3000 to 3001 still works), strips browser
// context and injects the API session read from VALUE_DATA_HOME.  CSP nonces
// are production-only (the dev client injects un-nonced scripts).
// VALUE_API_ORIGIN selects another local API (default http://127.0.0.1:8766).
function valueGateway(): Plugin {
  return {
    name: "value-ui-gateway",
    configureServer(server) {
      const gateway = createGateway({ apiOrigin: process.env.VALUE_API_ORIGIN || "http://127.0.0.1:8766", csp: false });
      server.middlewares.use((req, res, next) => gateway.handle(req, res, () => next()));
    },
  };
}

const SITE_CREATOR_PLACEHOLDER_DATABASE_ID =
  "00000000-0000-4000-8000-000000000000";

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

export default defineConfig(async () => {
  const server = isCodexSeatbeltSandbox
    ? { watch: { useFsEvents: false, usePolling: true } }
    : undefined;
  const hostingConfigPath = new URL("./.openai/hosting.json", import.meta.url);

  // Portable/local source releases do not contain a Sites deployment identity.
  // Vinext's Node build works with the same production launcher and needs no
  // Cloudflare bindings. Never create deployment metadata just to build locally.
  if (!existsSync(hostingConfigPath)) {
    return { server, plugins: [valueGateway(), vinext()] };
  }

  // The Sites deployment below has no local engine and does not mount the
  // VALUE gateway; the hosted page is not the research workbench's API path.

  // A configured Sites checkout retains its existing deployment plugin path.
  // Malformed configuration remains an error rather than silently changing target.
  const { d1, r2 } = JSON.parse(readFileSync(hostingConfigPath, "utf8")) as {
    d1?: string;
    r2?: string;
  };
  const localBindingConfig = {
    main: "./worker/index.ts",
    compatibility_flags: ["nodejs_compat"],
    d1_databases: d1
      ? [
          {
            binding: d1,
            database_name: "site-creator-d1",
            database_id: SITE_CREATOR_PLACEHOLDER_DATABASE_ID,
          },
        ]
      : [],
    r2_buckets: r2
      ? [
          {
            binding: r2,
            bucket_name: "site-creator-r2",
          },
        ]
      : [],
  };

  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  // Wrangler snapshots its log path while the Cloudflare plugin is imported.
  const [{ sites }, { cloudflare }] = await Promise.all([
    import("@openai/sites-vite-plugin"),
    import("@cloudflare/vite-plugin"),
  ]);

  return {
    server,
    plugins: [
      vinext(),
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        config: localBindingConfig,
      }),
    ],
  };
});

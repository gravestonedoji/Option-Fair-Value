# Option Fair Value Dashboard (Frontend)

React 18 + Vite 5 + TypeScript frontend for the Option Fair Value Dashboard.

## Stack

- React 18.3, Vite 5.3, TypeScript 5.4
- `@tanstack/react-query` v5 for server state
- `axios` for HTTP
- `tailwindcss` v3 (PostCSS) for styling
- `recharts` for charts (used in a later phase)
- `lucide-react` for icons
- `clsx` for conditional classes

## Getting started

```bash
npm install
cp .env.example .env   # adjust VITE_API_BASE_URL if needed
npm run dev            # starts Vite on http://localhost:5173
```

## Scripts

- `npm run dev` — start the Vite dev server
- `npm run build` — typecheck + production build
- `npm run preview` — preview the production build
- `npm run typecheck` — run `tsc --noEmit`

## Environment

| Variable             | Default            | Description                                                        |
| -------------------- | ------------------ | ------------------------------------------------------------------ |
| `VITE_API_BASE_URL`  | *(unset → same-origin)* | Only set for split deploys where the API lives on another host |

## Dev server proxy

The Vite dev server proxies all API routes (`/api`, `/expiries`, `/chain`,
`/fairvalue`, `/analysis`, `/alerts`, `/health`) to `http://localhost:8000`,
so API calls are same-origin and work without CORS from localhost, LAN, or
Tailscale. The server listens on all interfaces (`host: true`) and allows
this machine's hostname (e.g. `http://<hostname>:5173` via MagicDNS) plus
`*.ts.net` names so it can be reached over a tailnet (see the root README's
"Remote access with Tailscale").

## API contract

Defined in [`src/types.ts`](./src/types.ts). The backend is expected to conform.

- `GET /expiries/{symbol}` → `Expiries`
- `GET /chain/{symbol}?expiry=YYYY-MM-DD` → `OptionChain`
- `POST /fairvalue` (body: `FairValueRequest`) → `FairValueRange`

## Layout

- Top bar: title + `SymbolSearch` (with watchlist chips)
- Row: `ExpirySelector`
- Two-column layout (lg+): `OptionsChain` (~60%) | `FairValuePanel` (~40%)

## Status

`FairValuePanel` is currently a stub showing the selected contract summary.
The full fair-value UI (range chart, Greeks table, model comparison, input
bands) will be implemented in a later phase.

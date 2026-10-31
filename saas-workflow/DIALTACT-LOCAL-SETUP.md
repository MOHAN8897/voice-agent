# Dialtact AI — local setup with this backend

Frontend repo: [saiskm115/dialtact-app](https://github.com/saiskm115/dialtact-app)

## 1. Clone (sibling to voice agent)

```powershell
cd D:\
git clone https://github.com/saiskm115/dialtact-app.git
cd dialtact-app
copy .env.example .env
```

Edit `.env`:

```
VITE_API_URL=http://localhost:8000/api
```

## 2. Start backend

```powershell
cd "D:\voice agent"
# Ensure DATABASE_URL and migrations applied
uvicorn server.app:app --reload --port 8000
```

## 3. Start Dialtact

```powershell
cd D:\dialtact-app
npm install
npm run dev
```

Open http://localhost:5173

## 4. Stripe webhooks (number purchase)

See [PRD-11-stripe-cli-local-dev.md](./PRD-11-stripe-cli-local-dev.md).

## 5. API compatibility

Until Phase 1–2 backend work lands, Dialtact may hit missing routes (`/api/auth/signup`, `/api/telephony/buy`). Use [PRD-08-api-contract-mapping.md](./PRD-08-api-contract-mapping.md) as the implementation checklist.

Optional Vite proxy (if cookies/CORS are awkward):

```js
// vite.config.js — server.proxy
proxy: {
  '/api': { target: 'http://localhost:8000', changeOrigin: true },
}
```

Then set `VITE_API_URL=/api` or empty with relative paths in `api.js`.

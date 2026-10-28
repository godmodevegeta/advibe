# Deploy AdVibe on Render

The React frontend and FastAPI API run as one free Render Web Service.
No local Docker installation, separate frontend service, database, or paid cron resource is required.

## Publish

1. Push the deployment files to the `main` branch of `godmodevegeta/advibe`.
2. In Render, create a Blueprint from that repository and select the root `render.yaml`.
3. Supply the existing `QLOO_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODEL`, and `VITE_CARTO_API_KEY` when prompted.
4. Keep the configured `QLOO_BASE_URL` on the hackathon host.
5. Deploy, then open the HTTPS URL assigned by Render.

The Blueprint uses Python 3.13 and Node 24 through the repository version files.
The build installs Python dependencies and runs `npm ci` and the frontend production build.
The server starts on `0.0.0.0:$PORT` with one Uvicorn worker.
`SERVE_FRONTEND=true` enables production static hosting and makes startup fail if `dist/index.html` or the compiled assets are missing.
All API requests retain their existing `/api` URLs.
The health check is `/api/health` and never calls Qloo or the LLM.

Configure CARTO's website restrictions to allow the assigned hostname.
The CARTO key is browser-facing and is embedded at build time, so changing it requires a rebuild.
Qloo and LLM keys belong only in Render's backend environment settings.
Do not commit `.env` files or enter backend secrets as `VITE_` variables.
No Meta credentials are required and no Meta API calls are enabled.

## Verify before publishing

```sh
advibe-backend/.venv/bin/python -m pip install -r advibe-backend/requirements-dev.txt
cd advibe-backend
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
```

In the frontend directory, run `npm test`, `npm run lint`, and `npm run build`.
Then, from the repository root, run the compiled app without Vite:

```sh
SERVE_FRONTEND=true advibe-backend/.venv/bin/uvicorn stream_harness:app --app-dir advibe-backend --host 127.0.0.1 --port 8001 --workers 1
```

Open `http://127.0.0.1:8001`.
Verify the incomplete Ask flow, presets, progressive map and audience artifacts, latest trend snapshot, creative generation, and staged Meta campaign review.
Check desktop and mobile, reload the home page, and confirm separate browser sessions do not mix their campaign state.
Confirm missing assets and unknown `/api` paths return 404 rather than HTML.
Repeat the journey on the public URL after deployment, including progressive streaming and CARTO tiles.

The ordinary local development workflow remains the API on port 8000 and Vite on port 5173.
Leave `SERVE_FRONTEND` unset for that workflow.

## External keep-alive

Once the public URL is known, create an HTTP job on cron-job.org.
Set its URL to `https://YOUR-ASSIGNED-HOSTNAME/api/health`, method GET, and interval 10 minutes.
Do not send API credentials or request campaign generation from the scheduler.
Inspect successful executions and open the application again after at least 20 minutes without browser activity.

Render's free tier may still restart services and enforces monthly usage limits.
The scheduled request addresses idle sleep only.
Campaign state currently lives in each browser session and resets on page reload.
Durable projects, account login, and actual Meta deployment remain outside this release.

"""Production routing checks without external services or a frontend dev server."""

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import stream_harness as sh


class FrontendHostingTests(unittest.TestCase):
    def test_explicit_enable_and_missing_build(self):
        app = FastAPI()
        with tempfile.TemporaryDirectory() as folder:
            sh.configure_frontend(app, enabled=False, directory=Path(folder))
            with self.assertRaisesRegex(RuntimeError, "compiled frontend"):
                sh.configure_frontend(app, enabled=True, directory=Path(folder))

    def test_api_precedence_assets_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "assets").mkdir()
            (directory / "index.html").write_text("<html>AdVibe production</html>")
            (directory / "assets" / "app.js").write_text("console.log('app')")
            app = FastAPI()
            app.include_router(sh.app.router)
            sh.configure_frontend(app, enabled=True, directory=directory)
            with TestClient(app) as client:
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
                self.assertEqual(client.get("/api/health").json(), {"status": "ok"})
                self.assertEqual(len(client.get("/api/presets").json()["presets"]), 5)
                self.assertIn(
                    "javascript", client.get("/assets/app.js").headers["content-type"]
                )
                for path in (
                    "/api/unknown",
                    "/assets/missing.js",
                    "/.env",
                    "/render.yaml",
                    "/advibe-backend/.env",
                ):
                    self.assertEqual(client.get(path).status_code, 404, path)
                self.assertEqual(
                    client.post("/api/ask", json={"selected_seeds": 42}).status_code,
                    422,
                )

    def test_cors_allows_local_development_not_arbitrary_origins(self):
        with TestClient(sh.app) as client:
            for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
                response = client.options(
                    "/api/ask",
                    headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
                )
                self.assertEqual(
                    response.headers["access-control-allow-origin"], origin
                )
            response = client.options(
                "/api/ask",
                headers={
                    "Origin": "https://unrelated.example",
                    "Access-Control-Request-Method": "POST",
                },
            )
            self.assertNotIn("access-control-allow-origin", response.headers)

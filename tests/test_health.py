import unittest
from unittest.mock import patch

import httpx

from main import app, get_server_port


class HealthEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_endpoints_support_get_and_head(self):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            for path in ("/health", "/healthz"):
                with self.subTest(path=path):
                    get_response = await client.get(path)

                    self.assertEqual(get_response.status_code, 200)
                    self.assertEqual(
                        get_response.json(),
                        {"status": "healthy", "database": "turso"},
                    )

                    head_response = await client.head(path)
                    self.assertEqual(head_response.status_code, 200)
                    self.assertEqual(head_response.content, b"")

    def test_server_port_prefers_botkeep_assignment(self):
        with patch.dict(
            "os.environ",
            {"SERVER_PORT": "35175", "PORT": "8000"},
            clear=True,
        ):
            self.assertEqual(get_server_port(), 35175)

    def test_server_port_supports_port_fallback_and_local_default(self):
        with patch.dict("os.environ", {"PORT": "9000"}, clear=True):
            self.assertEqual(get_server_port(), 9000)

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(get_server_port(), 8000)


if __name__ == "__main__":
    unittest.main()

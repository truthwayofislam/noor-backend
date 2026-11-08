import unittest

import httpx

from main import app


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


if __name__ == "__main__":
    unittest.main()

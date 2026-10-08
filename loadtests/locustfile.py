"""Local CPU-only API workload. Never requests or approves remediation."""
import os
from locust import HttpUser, between, task


class IncidentUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers["X-API-Key"] = os.environ["SERVICE_API_KEY"]

    @task(1)
    def health(self):
        self.client.get("/health/ready")

    @task(3)
    def analyze(self):
        self.client.post("/api/incidents", json={
            "cell_id": "CELL_028_1",
            "start_time": "2026-08-05 07:00:00",
            "end_time": "2026-08-05 10:00:00",
            "backend": "csv", "rag": False,
        })

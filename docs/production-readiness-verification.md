# Production-readiness verification — 2026-10-08

Branch: `fix/rca-evidence-sufficiency`. No commits, pushes, deployments, Terraform apply, or AWS provisioning commands were executed. Original telecom dataset files were not changed. Pre-existing uncommitted work was preserved.

| Exact command | Result |
|---|---|
| `python -m unittest discover -s tests -v > /tmp/telecom-tests.log 2>&1` | Sandboxed FastAPI TestClient run stalled on its first request; interrupted. |
| `timeout 180 python -m unittest discover -s tests -v > /tmp/telecom-tests-final.log 2>&1` | Outside sandbox: exit 0, 33 tests passed in 11.697 s, Python 3.12.13; no skips. |
| `python -m scripts.validate_scenarios --output reports/rca.json > /tmp/telecom-evaluation.log 2>&1` | Exit 0; original 63/63 synthetic cause matches; separate suite 5/5 cause matches, 0/9 unsafe plans, 9/9 appropriate rejection, 2/2 expected RCA abstentions, one positive-control plan. |
| `env SERVICE_API_KEY=validation-only /snap/bin/docker-compose -f docker/docker-compose.yml config --quiet` | Outside sandbox: exit 0. Docker Compose plugin is absent; installed standalone Snap Compose used. Its sandboxed attempt failed on Snap runtime directory permissions. |
| `python -m py_compile loadtests/locustfile.py` | Exit 0; syntax only. Locust is not installed; no load run or throughput/latency benchmark. |
| `command -v terraform` | Terraform unavailable. `terraform -chdir=infra/terraform fmt -check`, `init -backend=false` and `validate` skipped; configuration not provider-validated. |
| `git diff --check` | Exit 0. |
| `git diff --name-only -- data/telecom_data` | Empty: original dataset unchanged. |

`docker build -t telecom-assurance:readiness . > /tmp/telecom-docker-build.log 2>&1` completed outside the sandbox with exit 0: image `f27ccdb71120`, tag `telecom-assurance:readiness`.

`docker run --rm -i --network none -e SERVICE_API_KEY=smoke-only --entrypoint python telecom-assurance:readiness - < /tmp/telecom-container-smoke.py > /tmp/telecom-container-smoke.log 2>&1` completed with exit 0. The temporary smoke script verified UID 10001, absence of `/app/.env` and `/app/reports`, readiness HTTP 200 and a CSV incident-analysis HTTP 200 with expected cause CONGESTION. No ports were published; the container was removed on exit. The first smoke attempt using a `/tmp` bind mount failed because the daemon could not see the script; stdin delivery succeeded. Script and logs are retained locally under ignored `reports/` for review. The initial sandbox build was blocked by Docker socket permissions. An authorized build was interrupted after its dependency resolver selected unused CUDA packages. Dockerfile and CI now install CPU-only PyTorch first, retaining existing application requirements.

Changed/added for this milestone:

- `.github/workflows/ci.yml`
- `.dockerignore`, `.gitignore`, `Dockerfile`, `docker/docker-compose.yml`
- `scripts/validate_scenarios.py`, `src/actions/simulator.py`
- `src/api/app.py`, `src/services/incident_store.py` (readiness endpoint/storage check)
- `tests/test_evaluation.py`, `tests/test_readiness.py`
- `tests/fixtures/rca_safety/{README.md,scenarios.csv,cell_kpi.csv,alarms.csv,configuration_changes.csv,tickets.csv}`
- `infra/terraform/{main.tf,README.md,terraform.tfvars.example}`
- `loadtests/{locustfile.py,requirements.txt}`
- `README.md`, `docs/production-readiness-verification.md`

`requirements.txt`, `tests/test_api.py`, `src/services/observability.py` and `tests/test_observability.py` already had uncommitted changes at task start and were not edited in this milestone. Other listed files also include preserved pre-existing changes, so the full working-tree diff is broader than this milestone.

Limits: synthetic regression agreement is not real-world ground truth; no production safety or load-performance claims. ECS is capped at one task with stop-before-start downtime and ephemeral SQLite/audit state. It does not provide durable/distributed idempotency. Optional RAG/PostgreSQL/model readiness, enterprise identity, live remediation and shared durable storage remain outside this milestone. Existing dependencies/base image are not fully locked; fresh builds may resolve different versions. CI configuration was added but not executed on GitHub.

# On-Call Operational Runbook

**Service:** `dev-platform-app`  
**Namespace:** `development`  
**Observability:** Prometheus, Grafana, Alertmanager (`monitoring` namespace)  
**Self-Healing Controller:** `remediation-service` (`monitoring` namespace)  

---

## Quick Reference / Emergency Actions

| Situation | First Response Command |
| :--- | :--- |
| **Roll back deployment immediately** | `kubectl -n development rollout undo deploy/dev-platform-app` |
| **Check pod status & crash reasons** | `kubectl -n development get pods -l app=platform-app -o wide` |
| **Inspect real-time container logs** | `kubectl -n development logs deploy/dev-platform-app --all-containers --tail=100 -f` |
| **View remediation audit trail** | `kubectl -n monitoring logs deploy/remediation-service \| grep AUDIT` |
| **Check Prometheus alert statuses** | Visit `http://localhost:9090/alerts` |
| **Check Grafana dashboards** | Visit `http://localhost:3000` |

---

## Table of Contents
1. [Alert: HighErrorRate](#high-error-rate)
2. [Alert: HighLatency](#high-latency)
3. [Alert: KubePodCrashLooping](#crash-looping)
4. [Alert: HPAAtMaxReplicas](#hpa-at-max-replicas)
5. [Alert: DeploymentReplicasMismatch](#deployment-replicas-mismatch)
6. [Alerts: SLOErrorBudgetFastBurn & SLOErrorBudgetSlowBurn](#slo-error-budget-burn)
7. [Alert: SLOLatencyBudgetBurn](#slo-latency-budget-burn)
8. [Remediation Service Troubleshooting](#remediation-service-troubleshooting)

---

<a name="high-error-rate"></a>
## 1. HighErrorRate

### Overview
- **Severity:** `critical`
- **Threshold:** > 5% of HTTP requests return `5xx` status codes over a 5-minute rolling window for at least 2 minutes.
- **User Impact:** End users receiving HTTP 500/502/503 errors. Degrades availability SLO.

### Diagnosis Steps
1. Identify which endpoints are failing:
   ```bash
   kubectl -n development exec deploy/dev-platform-app -- python -c "
   import urllib.request, re
   metrics = urllib.request.urlopen('http://localhost:8000/metrics').read().decode()
   for line in re.findall(r'http_requests_total.*status_code=\"5..\"[^\n]*', metrics):
       print(line)
   "
   ```
2. Query error rate in Prometheus:
   ```promql
   sum(rate(http_requests_total{namespace="development", status_code=~"5.."}[5m]))
   /
   sum(rate(http_requests_total{namespace="development"}[5m]))
   ```
3. Inspect recent application errors:
   ```bash
   kubectl -n development logs deploy/dev-platform-app --tail=200 | grep -E "ERROR|CRITICAL|Traceback"
   ```
4. Verify database connectivity (if `/db-check` is returning 500):
   ```bash
   kubectl -n development exec deploy/dev-platform-app -- python -c "
   import urllib.request
   try:
       r = urllib.request.urlopen('http://localhost:8000/db-check')
       print('DB OK:', r.read().decode())
   except Exception as e:
       print('DB Error:', e)
   "
   ```

### Remediation
- **If caused by a recent deployment:**
  Roll back to the previous stable revision:
  ```bash
  kubectl -n development rollout undo deploy/dev-platform-app
  ```
- **If caused by database unreachable:**
  Check RDS / PostgreSQL instance status and security group ingress rules:
  ```bash
  kubectl -n development get endpoints dev-platform-app-svc
  ```
- **If caused by external dependency panic:**
  Scale up temporarily to absorb retries or restart the deployment:
  ```bash
  kubectl -n development rollout restart deploy/dev-platform-app
  ```

---

<a name="high-latency"></a>
## 2. HighLatency

### Overview
- **Severity:** `warning`
- **Threshold:** 99th-percentile (p99) latency > 1.0s for 3 consecutive minutes (excluding `/slow`).
- **User Impact:** Sluggish UI/API responses, potential client timeouts.

### Diagnosis Steps
1. Check p99 latency in Prometheus:
   ```promql
   histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{namespace="development", endpoint!="/slow"}[5m])))
   ```
2. Check pod CPU and Memory throttling:
   ```bash
   kubectl top pods -n development -l app=platform-app
   ```
3. Check if HPA is scaling:
   ```bash
   kubectl -n development get hpa dev-platform-app-hpa
   ```

### Remediation
- **If pods are CPU-throttled:**
  Scale replicas up manually while HPA catches up:
  ```bash
  kubectl -n development scale deploy/dev-platform-app --replicas=4
  ```
- **If slow database queries:**
  Check DB active connections and query lock contention.

---

<a name="crash-looping"></a>
## 3. KubePodCrashLooping

### Overview
- **Severity:** `warning`
- **Threshold:** More than 3 container restarts in 15 minutes on any `dev-platform-app` pod.
- **Automated Action:** Handled by the Layer 3 Autonomous Remediation Webhook.

### Autonomous Remediation Ladder Workflow
1. **Restart 1 & 2:** Webhook patches deployment annotation (`restartedAt`) to trigger rolling restart.
2. **Rollback:** If restarts fail within 1 hour, webhook identifies the latest revision whose template genuinely differs (ignoring restart annotations) and rolls back automatically.
3. **Escalation:** If already rolled back or no earlier revision exists, notification is sent to Slack and human intervention is required.

### Manual Verification
1. Inspect the remediation audit trail:
   ```bash
   kubectl -n monitoring logs deploy/remediation-service | grep AUDIT
   ```
2. Check termination reason of the crashing container:
   ```bash
   kubectl -n development describe pod <crashing-pod-name> | grep -A 10 "Last State:"
   ```
3. Check previous pod logs prior to crash:
   ```bash
   kubectl -n development logs <crashing-pod-name> --previous --tail=100
   ```
4. If automated rollback did not trigger or was blocked by rate limit:
   ```bash
   kubectl -n development rollout undo deploy/dev-platform-app
   ```

---

<a name="hpa-at-max-replicas"></a>
## 4. HPAAtMaxReplicas

### Overview
- **Severity:** `warning`
- **Threshold:** HPA replica count has remained at `maxReplicas` (5) for > 5 minutes.
- **User Impact:** System has exhausted horizontal autoscaling headroom; traffic spikes may cause latency or 503 errors.

### Diagnosis Steps
1. Inspect HPA metrics:
   ```bash
   kubectl -n development describe hpa dev-platform-app-hpa
   ```
2. Determine if traffic increase is legitimate or a DDoS / crawler:
   ```promql
   sum(rate(http_requests_total{namespace="development"}[5m])) by (method, endpoint)
   ```

### Remediation
- Temporarily increase `maxReplicas`:
  ```bash
  kubectl -n development patch hpa dev-platform-app-hpa --type='json' -p='[{"op": "replace", "path": "/spec/maxReplicas", "value": 10}]'
  ```
- Update gitops base repository (`base/hpa.yaml`) for permanent capacity change.

---

<a name="deployment-replicas-mismatch"></a>
## 5. DeploymentReplicasMismatch

### Overview
- **Severity:** `warning`
- **Threshold:** `availableReplicas < desiredReplicas` for > 5 minutes.
- **User Impact:** Reduced fault-tolerance; violating PDB guarantees.

### Diagnosis Steps
1. Check replica availability:
   ```bash
   kubectl -n development get deploy dev-platform-app
   ```
2. Check cluster events for scheduling or node pressure issues:
   ```bash
   kubectl -n development get events --sort-by='.metadata.creationTimestamp' | tail -20
   ```
3. Verify node capacity:
   ```bash
   kubectl describe nodes | grep -A 8 "Allocated resources:"
   ```

### Remediation
- Check if nodes are in `NotReady` state or unschedulable (`minikube status`).
- Check image pull credentials (`ghcr-secret` secret existence).

---

<a name="slo-error-budget-burn"></a>
## 6. SLOErrorBudgetFastBurn & SLOErrorBudgetSlowBurn

### Overview
- **SLO Target:** 99.9% Successful Requests over a 30-day window (Error Budget = 0.1% or ~43.2 minutes downtime/month).
- **Fast Burn (Critical):** Burning budget at >14.4x across 1h & 5m windows (Entire monthly budget gone in ~50 hours). **Page on-call engineer immediately.**
- **Slow Burn (Warning):** Burning budget at >6.0x across 6h & 30m windows (Entire monthly budget gone in ~5 days).

### Immediate Actions
1. Silence non-critical deploy pipelines:
   Freeze new continuous delivery rollouts in ArgoCD (`platform-dev` app).
2. Check burn rate metrics in Prometheus:
   ```promql
   (1 - job:http_requests_success_rate:5m) / 0.001
   ```
3. Follow [HighErrorRate](#high-error-rate) triage protocol to isolate the cause.
4. Notify incident commander in `#incident-production`.

---

<a name="slo-latency-budget-burn"></a>
## 7. SLOLatencyBudgetBurn

### Overview
- **SLO Target:** 99% of requests < 500ms (30-day window).
- **Trigger:** p99 latency > 500ms sustained for > 5 minutes.

### Immediate Actions
1. Follow [HighLatency](#high-latency) triage protocol.
2. Determine if downstream dependency or database query degradation is the root cause.
3. Check container memory usage for near-OOM garbage collection thrashing.

---

<a name="remediation-service-troubleshooting"></a>
## 8. Remediation Service Troubleshooting

### Verifying Service Health
```bash
# Check pod status
kubectl -n monitoring get pods -l app=remediation-service

# Check health endpoint
kubectl -n monitoring exec deploy/remediation-service -- python -c "
import urllib.request
print(urllib.request.urlopen('http://localhost:5000/healthz').read().decode())
"

# Inspect metrics
kubectl -n monitoring exec deploy/remediation-service -- python -c "
import urllib.request
print(urllib.request.urlopen('http://localhost:5000/metrics').read().decode())
"
```

### Resetting Service State
The remediation service maintains its rate limits and action history in memory. If you need to immediately clear cooldowns or action counts during an emergency:
```bash
kubectl -n monitoring rollout restart deploy/remediation-service
```

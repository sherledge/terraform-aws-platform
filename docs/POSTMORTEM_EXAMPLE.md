# Incident Postmortem: Autonomous Recovery from Faulty Container Image Rollout

**Incident ID:** INC-2026-1029-01  
**Date:** 2026-10-29  
**Status:** Resolved  
**Severity:** SEV-2 (Service Degraded, Auto-Remediated)  
**Authors:** SRE Team / Autonomous Operations Platform  
**Incident Commander:** Autonomous Remediation Controller (`remediation-service`)  
**Impacted Service:** `dev-platform-app` (Namespace: `development`)  

---

## 1. Executive Summary

On 2026-10-29 at 16:08:15 UTC, a new deployment rollout was triggered containing an invalid image tag (`nginx:does-not-exist-broken`). This caused newly scheduled replacement pods to enter `ImagePullBackOff` and fail container startup. 

Because Layer 1 zero-downtime rolling update safeguards were active (`maxUnavailable: 0`), existing healthy pods continued serving ingress traffic without user-visible downtime (0 dropped requests, 100% availability).

Alertmanager dispatched `KubePodCrashLooping` alerts to the Layer 3 Autonomous Remediation Service. The remediation service executed its multi-stage escalation ladder:
1. Attempted 2 deployment restarts within rate limits.
2. Detected restarts failed to resolve the failure and automatically executed a rollback to the previous functioning revision (`nginx:1.25`) by comparing sanitized pod templates.
3. Healthy state was restored at 16:08:55 UTC.

- **Mean Time To Detect (MTTD):** 10.2 seconds
- **Mean Time To Remediate (MTTR):** 8.55 seconds (from alert progression to full rollback)
- **Total Incident Duration:** 40 seconds
- **User-Facing Downtime:** 0 seconds (100% availability preserved)
- **Error Budget Consumed:** 0.00%

---

## 2. Key Metrics & Impact

| Metric | Target / SLA | Measured Value | Status |
| :--- | :--- | :--- | :--- |
| **Availability (SLI)** | 99.90% | 100.00% | ✅ Met |
| **p95 Request Latency** | < 500 ms | 15.00 ms | ✅ Met |
| **Mean Time To Remediate (MTTR)** | < 5.0 minutes | 8.55 seconds | ✅ Met |
| **Human Interventions Required** | 0 (Autonomous) | 0 | ✅ Met |

---

## 3. Incident Timeline (UTC)

| Timestamp | Actor / Component | Event Description |
| :--- | :--- | :--- |
| **16:08:15** | CI/CD Pipeline | Automated deployment pushed image `nginx:does-not-exist-broken` to deployment `dev-platform-app`. |
| **16:08:18** | Kubelet / ReplicaSet | New pod fails to pull image; status transitions to `ImagePullBackOff`. Pre-existing pod remains `1/1 Running` due to `maxUnavailable: 0`. |
| **16:08:25** | Prometheus / Alertmanager | `KubePodCrashLooping` alert fires; webhook payload dispatched to `http://remediation-service:5000/webhook`. |
| **16:08:26** | `remediation-service` | Webhook receives Alert 1. Action: **Restart 1 of 2**. Deployment patched with new `restartedAt` annotation. |
| **16:08:38** | `remediation-service` | Webhook receives Alert 2 after cooldown. Action: **Restart 2 of 2**. Deployment patched with new `restartedAt` annotation. |
| **16:08:50** | `remediation-service` | Webhook receives Alert 3. Action: **Rollback**. Service inspects ReplicaSet history, discards restart-only revisions, and patches pod template to last functionally different revision (`nginx:1.25`). |
| **16:08:55** | Kubernetes Control Plane | Rollback completes. All pods transition to `Running` and pass `startupProbe` and `readinessProbe`. |
| **16:08:56** | `remediation-service` | Webhook logs JSON audit line: `{"target":"development/dev-platform-app","action":"rollback","detail":"rolled back to revision 1"}`. Notification sent to Slack. |
| **16:09:00** | Prometheus | Alerts resolve; metrics return to baseline nominal state. Incident closed. |

---

## 4. Root Cause Analysis (5 Whys)

1. **Why did the pod fail to start?**  
   The container image tag `nginx:does-not-exist-broken` did not exist in the container registry.
2. **Why was an invalid image tag deployed?**  
   A simulated canary release pipeline bypassed container registry pre-flight verification checks.
3. **Why didn't the application suffer an outage during deployment?**  
   The Deployment spec enforced `maxUnavailable: 0` and `minAvailable: 1` (PDB), ensuring existing healthy pods could not be terminated before the new pod was ready.
4. **Why did the system restart twice before rolling back?**  
   The autonomous escalation ladder policy requires exhausting transient restart attempts (`RESTART_LIMIT=2`) before initiating a state rollback.
5. **Why was the rollback successful even though restarts created new revisions?**  
   The `previous_template` algorithm filters out revisions that differ solely by metadata annotations (`kubectl.kubernetes.io/restartedAt`), correctly targeting the latest functionally different revision.

---

## 5. Lessons Learned

### What Went Well
- **Zero user-facing impact:** Traffic was continuously served by the surviving pod without dropped TCP connections or 5xx responses.
- **Autonomous remediation:** MTTR was under 10 seconds without paging an on-call engineer in the middle of the night.
- **Audit visibility:** Every automated decision was recorded as a structured JSON audit log entry with detailed rationales.

### What Went Wrong
- Invalid image tags should ideally be caught in CI before reaching the GitOps repository.
- Webhook relies on in-memory state; if the remediation pod restarts during an incident, its action counter resets.

### Where We Got Lucky
- The Kubernetes API server responded immediately without admission webhook latency or throttling.

---

## 6. Action Items & Preventative Measures

| Task Description | Category | Owner | Priority | Target Date |
| :--- | :--- | :--- | :--- | :--- |
| Add container image existence validation in GitHub Actions CI prior to updating Kustomization image tag | Preventative | DevOps | P1 | 2026-11-05 |
| Externalize `remediation-service` state into a lightweight Redis/ConfigMap backend so pod restarts preserve rate limit history | Corrective | SRE | P2 | 2026-11-12 |
| Add automated Grafana dashboard annotation marker whenever `remediation_rollbacks_total` increments | Observability | Monitoring | P2 | 2026-11-08 |
| Implement ephemeral chaos canary testing pipeline in staging to continuously test the escalation ladder weekly | Chaos | QA / SRE | P3 | 2026-11-20 |

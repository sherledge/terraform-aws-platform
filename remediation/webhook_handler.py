import os
import json
import time
import logging
import threading
import urllib.request
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

try:
    config.load_incluster_config()
except Exception:
    config.load_kube_config()

core = client.CoreV1Api()
apps = client.AppsV1Api()
api_client = client.ApiClient()

# --- Settings (override with environment variables) ---
REMEDIABLE = {"PodCrashLooping", "KubePodCrashLooping"}
ALLOWED_NAMESPACES = set(os.getenv("ALLOWED_NAMESPACES", "development").split(","))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
RESTART_LIMIT = int(os.getenv("RESTART_LIMIT", "2"))
MAX_ACTIONS_PER_HOUR = int(os.getenv("MAX_ACTIONS_PER_HOUR", "6"))
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
WINDOW = 3600  # one hour
RESTARTED_AT = "kubectl.kubernetes.io/restartedAt"
REVISION = "deployment.kubernetes.io/revision"

# --- State (in memory, single process) ---
_state = {}
_actions = []
_lock = threading.Lock()

# --- Metrics ---
ALERTS_RECEIVED = Counter(
    "remediation_alerts_received_total", "Alerts received from Alertmanager")
RESTARTS = Counter(
    "remediation_restarts_total", "Deployment restarts triggered",
    ["namespace", "deployment"])
ROLLBACKS = Counter(
    "remediation_rollbacks_total", "Deployment rollbacks triggered",
    ["namespace", "deployment"])
ESCALATIONS = Counter(
    "remediation_escalations_total", "Alerts escalated to a human",
    ["namespace", "deployment"])
SKIPPED = Counter(
    "remediation_skipped_total", "Alerts skipped, by reason", ["reason"])
API_ERRORS = Counter(
    "remediation_api_errors_total", "Kubernetes API errors during remediation")

for _reason in ("not_firing", "not_remediable", "namespace_not_allowed",
                "no_owner", "cooldown", "rate_limited"):
    SKIPPED.labels(reason=_reason)


# --- Helpers ---
def audit(**event):
    event["time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    logging.info("AUDIT %s", json.dumps(event))


def notify(text):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        logging.warning("Slack notification failed: %s", e)


def recent(timestamps, now):
    return [t for t in timestamps if now - t < WINDOW]


def owning_deployment(namespace, pod_name):
    pod = core.read_namespaced_pod(pod_name, namespace)
    for ref in pod.metadata.owner_references or []:
        if ref.kind == "ReplicaSet":
            rs = apps.read_namespaced_replica_set(ref.name, namespace)
            for rref in rs.metadata.owner_references or []:
                if rref.kind == "Deployment":
                    return rref.name
    return None


def clean_template(template):
    """Pod template as a dict, minus the bits that change on every restart."""
    t = api_client.sanitize_for_serialization(template)
    meta = t.setdefault("metadata", {})
    labels = meta.get("labels", {})
    labels.pop("pod-template-hash", None)
    annotations = meta.get("annotations", {})
    annotations.pop(RESTARTED_AT, None)
    if not annotations:
        meta.pop("annotations", None)
    return t


def previous_template(namespace, name):
    """Latest older revision whose template really differs from the current one."""
    dep = apps.read_namespaced_deployment(name, namespace)
    current_rev = int((dep.metadata.annotations or {}).get(REVISION, "0"))
    current = json.dumps(clean_template(dep.spec.template), sort_keys=True)
    selector = ",".join(f"{k}={v}" for k, v in (dep.spec.selector.match_labels or {}).items())

    candidates = []
    for rs in apps.list_namespaced_replica_set(namespace, label_selector=selector).items:
        owned = any(r.kind == "Deployment" and r.name == name
                    for r in rs.metadata.owner_references or [])
        rev = int((rs.metadata.annotations or {}).get(REVISION, "0"))
        if owned and 0 < rev < current_rev:
            candidates.append((rev, rs))

    for rev, rs in sorted(candidates, key=lambda c: c[0], reverse=True):
        template = clean_template(rs.spec.template)
        if json.dumps(template, sort_keys=True) != current:
            return rev, template
    return None, None


def do_restart(namespace, name):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"spec": {"template": {"metadata": {"annotations": {RESTARTED_AT: stamp}}}}}
    apps.patch_namespaced_deployment(name=name, namespace=namespace, body=body)


def do_rollback(namespace, name):
    revision, template = previous_template(namespace, name)
    if template is None:
        return None
    patch = [{"op": "replace", "path": "/spec/template", "value": template}]
    apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
    return revision


def remediate(namespace, deployment):
    key = f"{namespace}/{deployment}"
    with _lock:
        now = time.time()
        s = _state.setdefault(key, {"restarts": [], "rollbacks": [], "last_action": 0.0})
        s["restarts"] = recent(s["restarts"], now)
        s["rollbacks"] = recent(s["rollbacks"], now)
        _actions[:] = recent(_actions, now)

        if now - s["last_action"] < COOLDOWN_SECONDS:
            SKIPPED.labels(reason="cooldown").inc()
            logging.info("Cooldown active for %s", key)
            return None
        if len(_actions) >= MAX_ACTIONS_PER_HOUR:
            SKIPPED.labels(reason="rate_limited").inc()
            audit(target=key, action="skip", reason="rate_limited")
            return None

        try:
            if s["rollbacks"]:
                action = "escalate"
                detail = "already rolled back in the last hour and still failing"
            elif len(s["restarts"]) >= RESTART_LIMIT:
                revision = do_rollback(namespace, deployment)
                if revision is None:
                    action = "escalate"
                    detail = "restarts did not help and there is no earlier version to roll back to"
                else:
                    action = "rollback"
                    detail = f"rolled back to revision {revision}"
                    s["rollbacks"].append(now)
            else:
                do_restart(namespace, deployment)
                s["restarts"].append(now)
                action = "restart"
                detail = f"restart {len(s['restarts'])} of {RESTART_LIMIT} allowed per hour"
        except ApiException as e:
            API_ERRORS.inc()
            audit(target=key, action="error", reason=e.reason)
            logging.error("Kubernetes API error for %s: %s", key, e.reason)
            return None

        s["last_action"] = now
        if action != "escalate":
            _actions.append(now)

    # Bookkeeping and notifications happen outside the lock
    counter = {"restart": RESTARTS, "rollback": ROLLBACKS, "escalate": ESCALATIONS}[action]
    counter.labels(namespace=namespace, deployment=deployment).inc()
    audit(target=key, action=action, detail=detail)
    icon = {"restart": ":arrows_counterclockwise:", "rollback": ":rewind:",
            "escalate": ":rotating_light:"}[action]
    notify(f"{icon} {key}: {action} - {detail}")
    return {"target": key, "action": action, "detail": detail}


# --- Routes ---
@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "healthy"}), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)


@app.route("/webhook", methods=["POST"])
def handle_alert():
    data = request.get_json(silent=True) or {}
    results = []

    for alert in data.get("alerts", []):
        ALERTS_RECEIVED.inc()
        labels = alert.get("labels", {})

        if alert.get("status") != "firing":
            SKIPPED.labels(reason="not_firing").inc()
            continue
        if labels.get("alertname") not in REMEDIABLE:
            SKIPPED.labels(reason="not_remediable").inc()
            continue

        namespace = labels.get("namespace")
        if namespace not in ALLOWED_NAMESPACES:
            logging.info("Skipping %s: namespace %s not allowed", labels.get("alertname"), namespace)
            SKIPPED.labels(reason="namespace_not_allowed").inc()
            continue

        try:
            deployment = labels.get("deployment")
            if not deployment and labels.get("pod"):
                deployment = owning_deployment(namespace, labels["pod"])
        except ApiException as e:
            API_ERRORS.inc()
            logging.error("Kubernetes API error for %s: %s", labels, e.reason)
            continue
        if not deployment:
            logging.warning("No owning deployment found for %s", labels)
            SKIPPED.labels(reason="no_owner").inc()
            continue

        result = remediate(namespace, deployment)
        if result:
            results.append(result)

    acted = [r for r in results if r["action"] in ("restart", "rollback")]
    status = "remediated" if acted else ("escalated" if results else "ignored")
    return jsonify({"status": status, "actions": results}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

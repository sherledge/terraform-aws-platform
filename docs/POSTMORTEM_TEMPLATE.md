# Incident Postmortem Template

**Incident ID:** INC-YYYY-MMDD-XX  
**Date:** YYYY-MM-DD  
**Status:** [Investigating / Identified / Resolved]  
**Severity:** [SEV-1 / SEV-2 / SEV-3]  
**Authors:** [Names / Roles]  
**Incident Commander:** [Name]  
**Impacted Services:** [Service Names / Namespaces]  

---

## 1. Executive Summary
*A 1-2 paragraph high-level overview of what happened, customer impact, root cause, and how it was resolved. Keep it accessible to non-technical stakeholders.*

- **Mean Time To Detect (MTTD):** 
- **Mean Time To Remediate (MTTR):** 
- **Total Incident Duration:** 
- **User-Facing Downtime:** 
- **Error Budget Consumed:** 

---

## 2. Key Metrics & Impact

| Metric | Target / SLA | Measured Value During Incident | Status |
| :--- | :--- | :--- | :--- |
| **Availability (SLI)** | 99.90% | | |
| **p95 / p99 Latency** | | | |
| **Requests Failed / Dropped** | 0 | | |
| **Customers Impacted** | 0 | | |

---

## 3. Incident Timeline (UTC)

| Timestamp | Actor / Component | Event Description |
| :--- | :--- | :--- |
| **HH:MM:SS** | Component | Initial failure / trigger event occurred. |
| **HH:MM:SS** | Alertmanager | Alert fired (`AlertName`). |
| **HH:MM:SS** | Controller / Engineer | Remediation action attempted. |
| **HH:MM:SS** | System | Recovery confirmed. Metrics normalized. |
| **HH:MM:SS** | Incident Commander | Incident officially closed. |

---

## 4. Root Cause Analysis (5 Whys)

1. **Why?** 
2. **Why?** 
3. **Why?** 
4. **Why?** 
5. **Why?** *(Root cause statement)*

---

## 5. Lessons Learned

### What Went Well
- 

### What Went Wrong
- 

### Where We Got Lucky
- 

---

## 6. Action Items (Preventative & Corrective)

| Task Description | Category | Owner | Priority | Target Date | Tracking Issue |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Fix root cause defect | Corrective | | P1 | | |
| Add missing alert / monitor | Observability | | P2 | | |
| Update runbook documentation | Documentation | | P2 | | |
| Add automated chaos test | Prevention | | P3 | | |

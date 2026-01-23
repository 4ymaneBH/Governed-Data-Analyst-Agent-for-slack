# Threat Model

This document describes security threats, mitigations, and residual risks for the Governed Data Analyst Agent.

## System Overview

The system allows business users to ask natural language questions about company data via Slack. An LLM interprets questions and calls governed tools to retrieve data, with all actions logged and policy-controlled.

## Assets

| Asset | Sensitivity | Description |
|-------|-------------|-------------|
| Customer PII | HIGH | Email, phone, address in raw schema |
| Payment Data | HIGH | Card numbers, payment methods |
| Business Metrics | MEDIUM | Revenue, CAC, churn data |
| User Credentials | HIGH | Slack tokens, DB passwords |
| Audit Logs | MEDIUM | Action history, compliance evidence |

## Threat Actors

| Actor | Capability | Motivation |
|-------|------------|------------|
| Malicious Insider | Has valid Slack access | Data exfiltration |
| Compromised Account | Stolen Slack credentials | Unauthorized access |
| Curious Employee | Valid low-privilege access | Privilege escalation |
| LLM Prompt Injection | Crafted input | Bypass controls |

---

## Threats & Mitigations

### T1: Unauthorized Data Access

**Description:** User attempts to access data beyond their role permissions.

**Attack Vectors:**
- Direct SQL injection via question
- Requesting PII columns
- Accessing restricted schemas

**Mitigations:**
- ✅ OPA RBAC policies
- ✅ Schema-level access control
- ✅ Column-level PII blocking
- ✅ Query parsing and validation
- ✅ All queries logged

**Residual Risk:** LOW

---

### T2: Privilege Escalation

**Description:** User attempts to elevate their role or bypass RLS.

**Attack Vectors:**
- Manipulating role in API requests
- Bypassing region filters (sales)
- Impersonating another user

**Mitigations:**
- ✅ Role derived from Slack user ID
- ✅ Postgres RLS enforced at DB level
- ✅ Context validated per request
- ✅ Session-based user binding

**Residual Risk:** LOW

---

### T3: Prompt Injection

**Description:** LLM is tricked into bypassing safety controls.

**Attack Vectors:**
- Embedding instructions in questions
- Retrieved docs contain malicious prompts
- SQL injection via LLM generation

**Mitigations:**
- ✅ LLM cannot directly call tools - agent decides
- ✅ Generated SQL parsed before execution
- ✅ Policy check AFTER query generation
- ✅ Retrieved docs don't trigger tool calls
- ⚠️ LLM could generate harmful SQL (mitigated by parsing)

**Residual Risk:** MEDIUM

---

### T4: Data Exfiltration

**Description:** User extracts large amounts of sensitive data.

**Attack Vectors:**
- Large unbounded queries
- Multiple small queries aggregated
- Export functionality abuse

**Mitigations:**
- ✅ LIMIT enforcement on queries
- ✅ Large result sets require approval
- ✅ All queries logged with row counts
- ✅ Rate limiting (can be added)
- ⚠️ Aggregated small queries not detected

**Residual Risk:** MEDIUM

---

### T5: Audit Log Tampering

**Description:** Attacker modifies or deletes audit logs.

**Attack Vectors:**
- Direct database access
- Compromised admin account
- Log deletion

**Mitigations:**
- ✅ Audit logs in separate table
- ✅ App uses limited DB permissions
- ⚠️ Admin can delete logs (would need append-only log)
- ⚠️ No log integrity verification (would need signing)

**Residual Risk:** MEDIUM

---

### T6: Credential Exposure

**Description:** API keys or database credentials are leaked.

**Attack Vectors:**
- Credentials in code/logs
- Environment variable exposure
- Container image inspection

**Mitigations:**
- ✅ Credentials in environment variables
- ✅ .gitignore for .env files
- ✅ PII redacted from logs
- ⚠️ Docker compose on disk has default credentials

**Residual Risk:** MEDIUM (for local dev)

---

### T7: Denial of Service

**Description:** System availability degraded by abuse.

**Attack Vectors:**
- Expensive queries
- High request volume
- LLM resource exhaustion

**Mitigations:**
- ⚠️ Query timeout not implemented
- ⚠️ Rate limiting not implemented
- ✅ Ollama local (not billing attack)
- ✅ Async processing

**Residual Risk:** MEDIUM

---

### T8: Supply Chain Attack

**Description:** Compromised dependencies introduce vulnerabilities.

**Attack Vectors:**
- Malicious Python packages
- Compromised Docker images
- LLM model poisoning

**Mitigations:**
- ⚠️ No dependency pinning (should add)
- ⚠️ No vulnerability scanning (should add)
- ✅ Official Docker images used
- ✅ Ollama models from official registry

**Residual Risk:** MEDIUM

---

## Risk Matrix

| Threat | Likelihood | Impact | Risk | Status |
|--------|------------|--------|------|--------|
| T1: Unauthorized Access | LOW | HIGH | MEDIUM | ✅ Mitigated |
| T2: Privilege Escalation | LOW | HIGH | MEDIUM | ✅ Mitigated |
| T3: Prompt Injection | MEDIUM | MEDIUM | MEDIUM | ⚠️ Partially |
| T4: Data Exfiltration | MEDIUM | HIGH | HIGH | ⚠️ Partially |
| T5: Audit Tampering | LOW | MEDIUM | LOW | ⚠️ Partially |
| T6: Credential Exposure | MEDIUM | HIGH | HIGH | ⚠️ Partially |
| T7: Denial of Service | MEDIUM | LOW | LOW | ⚠️ Not mitigated |
| T8: Supply Chain | LOW | HIGH | MEDIUM | ⚠️ Not mitigated |

---

## Recommendations

### High Priority

1. **Add rate limiting** - Prevent abuse and data exfiltration
2. **Pin dependencies** - Prevent supply chain attacks
3. **Add query timeouts** - Prevent expensive query DoS

### Medium Priority

4. **Implement append-only audit logs** - Use write-only credentials
5. **Add log integrity verification** - Sign audit entries
6. **Scan dependencies** - Use Dependabot/Snyk

### Low Priority

7. **Add anomaly detection** - Alert on unusual query patterns
8. **Implement break-glass procedures** - Emergency access revocation
9. **Add data masking for exports** - Prevent PII in exports

---

## Compliance Considerations

| Requirement | Status |
|-------------|--------|
| Access Control | ✅ RBAC + RLS implemented |
| Audit Logging | ✅ Full logging with redaction |
| Data Minimization | ✅ Column blocking + masking |
| Purpose Limitation | ⚠️ Not enforced |
| Retention | ⚠️ No retention policy |
| Encryption at Rest | ⚠️ Not configured |
| Encryption in Transit | ⚠️ HTTP only (add TLS) |

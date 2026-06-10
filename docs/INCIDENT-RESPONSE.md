# Incident Response Playbook — trentpower.fr

Scope: Static, privacy-first personal site hosted on Gandi (Apache + Varnish).  
No dynamic content. No user data stored. No external integrations.

This playbook covers detection and response if something appears wrong.

---

## 1. Possible Incidents

### A. Unexpected Content Change

- Page content altered
- Unknown script present
- Layout or behaviour changed unexpectedly

### B. Header Misconfiguration

- Missing CSP
- COEP or COOP removed
- HSTS missing

### C. Integrity Mismatch

- `integrity.json` hash no longer matches deployed files
- Signature verification fails

### D. TLS / Certificate Warning

- Browser reports insecure connection

### E. DNS Hijack / Redirect

- Domain resolves elsewhere
- Unexpected redirect behaviour

---

## 2. Immediate Actions

### Step 1 — Freeze

Do not edit files immediately.

First determine whether this is:

- Cache propagation
- Local browser issue
- Real server-side change

Test from:

- Private browser window
- Different device
- Different network (mobile hotspot)

---

### Step 2 — Verify Integrity

Download:

```
/integrity.json
```

Recompute hash locally for a suspicious file:

```
openssl dgst -sha256 -binary file.ext | openssl base64
```

Compare with the `integrity.json` entry.

If mismatch:

- Deployment integrity compromised
- Continue to Step 3

If match:

- Likely cache or local issue

---

### Step 3 — Lock Down Access

Immediately:

- Log into Gandi admin
- Change account password
- Confirm 2FA enabled
- Review recent login activity
- Revoke unknown sessions

If necessary:

- Disable SFTP temporarily

---

### Step 4 — Replace Site With Known-Good Copy

From local repository:

1. Re-upload full site
2. Regenerate `integrity.json`
3. Sign it
4. Upload new manifest + signature

Then:

- Purge Varnish cache via Gandi panel

---

### Step 5 — Audit Environment

Check:

- Registrar account access logs
- DNS settings unchanged
- TLS certificate status
- Apache file timestamps
- No unknown files in root directory

Remove any unknown files.

---

## 3. If TLS Warning Appears

- Check Gandi certificate status
- Confirm domain not expired
- Verify DNS not altered

Do not attempt to fix via `.htaccess`.

TLS is infrastructure-level.

---

## 4. If DNS Appears Hijacked

Immediately:

- Log into domain registrar
- Change registrar password
- Enable registry lock if available
- Verify nameserver entries
- Contact registrar support

---

## 5. Key Compromise Scenario (PGP)

If private signing key suspected compromised:

1. Generate new key
2. Revoke old key
3. Publish revocation certificate
4. Update `/pgp.txt`
5. Re-sign `integrity.json`
6. Update integrity page with note

---

## 6. Communication Policy

If incident affects integrity:

Update:

- `/integrity/index.html`

Add short factual note:

- Date
- What changed
- Confirmation of remediation
- No speculation

Keep tone factual.

---

## 7. What Is Not an Incident

- Temporary cache inconsistencies
- Varnish serving stale HTML briefly
- Browser extension warnings unrelated to site
- Lighthouse score fluctuations

Do not overreact.

---

## 8. Recovery Confirmation Checklist

Before declaring resolved:

- Headers verified via httpstatus.io
- Integrity manifest matches deployed files
- Signature verifies
- No unknown files present
- All governance pages intact
- No third-party requests introduced

---

## 9. Prevention

- Hardware-backed 2FA on Gandi and email
- Unique passwords
- Private key stored offline
- Annual audit
- Minimal change frequency

Stability reduces risk.

---

## 10. Philosophy

This site has no user accounts, no stored data, no dynamic surface.

Most incidents would be limited to:

- Content tampering
- DNS manipulation
- Hosting account compromise

The architecture is intentionally small to keep response simple.

If something breaks, restore from a known-good state.

Do not improvise.

# MIPS and release eligibility (development preview)

Five founder-designated mandatory integrated platform systems:
1. GoreeCloud UI
2. Wardveil
3. GoreeShield
4. GoreeCloud Identity
5. GoreeCloud Mesh

| Platform | Verified code boundary | Remaining acceptance |
| --- | --- | --- |
| GoreeCloud UI | Responsive web CSS maps GC UI Canvas/Surface/Lens, color and spacing semantics | Full screenshot-led, accessibility, device, typography and theme acceptance |
| Wardveil | No enforcement or integration | Assess audit/security telemetry and allowed event payloads |
| GoreeShield | No enforcement integration | Verify applicable hardening and least-privilege integration |
| GoreeCloud Identity | Local bearer-token development mode only | OIDC, scoped authorization, authentication/account recovery |
| GoreeCloud Mesh | No cross-product events | Document/authorization event integration review |

The project is not Stable, Anchor or production-deployed. CI unit tests cannot establish recovery readiness, multiuser security, native OS acceptance, overall GC UI compliance or external model-host interoperability.

Before production: scoped identity, sharing authorization policy, TLS reverse proxy, secure secrets, rate limits, database backup and disaster recovery rehearsal, audit logs, real-device browser and native tests, supply-chain scanning, policy review, failover and rollback verification, plus appropriate five-MIPS assessment.

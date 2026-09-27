# Security reporting

For a suspected vulnerability, use this repository's **Security → Report a vulnerability** private reporting route when enabled. Include affected commit/version, a minimal synthetic reproduction, impact and suggested mitigation. Do not include real company data or live credentials. Do not disclose exploit details in a public issue.

The maintainer reviews reports on a best-effort basis; this portfolio project has no guaranteed security response SLA. The current maintained line is the latest `0.1.x` candidate/release. Older commits are not independently supported.

Local development tokens and default database passwords are for loopback-only synthetic demonstrations. Internet-facing deployments require the documented identity, network, storage and operational controls. Automated tests and vulnerability scans are bounded evidence, not independent penetration testing or production acceptance. See [the threat model](docs/threat_model.md) and [release acceptance](docs/portfolio/acceptance.md).

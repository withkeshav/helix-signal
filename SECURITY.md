# Security Policy

## Reporting a Vulnerability

If you discover a security issue, please report it privately before opening a public issue.

Please include:

- A clear description of the vulnerability
- Steps to reproduce
- Impact assessment
- Any suggested remediation

For now, submit reports to the project maintainers through a private channel you control (email or direct message).
If no private channel is available, open a minimal public issue without exploit details and request a secure contact path.

## Scope Notes

Helix-Signal is a monitoring/data project and does not provide custody, wallet, or transaction signing features in V1.
Security priorities still include:

- Dependency hygiene
- Safe handling of environment variables
- Avoiding accidental secret disclosure in commits/issues
- Defensive error handling for external API failures

# Security

## Reporting a vulnerability

Use the repository's **Security > Advisories > Report a vulnerability** option
to report suspected vulnerabilities privately. Avoid posting credentials,
personal data, or exploit details in public issues. If private reporting is
unavailable, contact the maintainer at bdrapeau@gxpframe.com.

## Deployment configuration

Keep provider keys, database credentials, the administrator access key, and
session-signing secrets outside Git and in the deployment provider's secret
store. Use the checked-in `.env.example` files as templates. Variables prefixed
with `VITE_` are public browser configuration and must never contain secrets.

Public player access is separate from administrator authentication. Production
must keep `AUTH_REQUIRED=true`; `PUBLIC_PLAYER_ACCESS=true` opens player
workflows while operational endpoints still require administrator sessions.
The production AI budget and request limits remain in force.

If a secret is committed, revoke or rotate it before attempting history cleanup.
Removing a file from the latest commit does not remove earlier copies.

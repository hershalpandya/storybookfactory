# Security

Use [GitHub private vulnerability reporting](https://github.com/hershalpandya/storybookfactory/security/advisories/new) to report suspected vulnerabilities. Include the affected version or commit and enough detail to identify the issue. Keep transcripts, artwork, credentials and private project paths out of reports shared beyond the owner.

## Local projects and credentials

Keep private story projects outside Git: `projects/` and `reports/` are ignored. Keep private security working documents in `reports/`. GitHub Actions checks out the toolkit and excludes these directories. Keep provider keys in the supported environment or macOS Keychain. Avoid storing credentials in project manifests, logs or prompts. Treat projects received from others as untrusted input and inspect them before running the toolkit.

## Dependency scanning

GitHub Actions runs Grype on pushes to `main`, pull requests, manual runs and a weekly schedule. The scan catalogs packages from `uv.lock`, including development dependencies and versions selected for other supported Python versions. High and critical findings fail the job. Download the JSON report from the workflow run. Review affected versions and available fixes before making lockfile updates.

Run the equivalent scan from a clean checkout with Grype installed.

```sh
grype dir:. --fail-on high --output table
```

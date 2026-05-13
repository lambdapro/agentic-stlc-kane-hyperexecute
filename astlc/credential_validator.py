"""
CredentialValidator — pre-flight validation for all pipeline credentials.

Checks GITHUB_TOKEN, LT_USERNAME, LT_ACCESS_KEY, and repo URL before
execute() begins so the platform fails fast with actionable guidance
rather than silently falling back to dry-run mode.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CredentialReport:
    github_token: bool = False
    github_token_scope: str = ""       # "repo", "public_repo", "unknown"
    lt_username: bool = False
    lt_access_key: bool = False
    lt_credentials_valid: Optional[bool] = None   # None = not checked
    repo_url: bool = False
    repo_slug: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def can_push(self) -> bool:
        return self.github_token and self.repo_url

    @property
    def can_trigger(self) -> bool:
        return self.github_token and self.repo_url

    @property
    def can_run_he(self) -> bool:
        return self.lt_username and self.lt_access_key

    @property
    def ready(self) -> bool:
        return bool(self.errors) is False

    def onboarding_message(self) -> str:
        """Return actionable markdown for the user when credentials are missing."""
        lines = ["## Credential Setup Required", ""]

        if not self.github_token:
            lines += [
                "### GitHub Token (`GITHUB_TOKEN`)",
                "Required to push generated tests and trigger the CI pipeline.",
                "",
                "```bash",
                "# Generate a token at: https://github.com/settings/tokens",
                "# Grant scopes: repo, workflow",
                "export GITHUB_TOKEN=ghp_...",
                "```",
                "",
            ]

        if not self.repo_url:
            lines += [
                "### Repository URL",
                "Specify your GitHub repository so the platform knows where to push.",
                "",
                "```bash",
                "agentic-stlc chat --requirements reqs.txt \\",
                "    --repo https://github.com/your-org/your-repo",
                "```",
                "",
                "Or set it permanently in `agentic-stlc.config.yaml`:",
                "```yaml",
                "project:",
                "  repository: https://github.com/your-org/your-repo",
                "```",
                "",
            ]

        if not self.lt_username or not self.lt_access_key:
            lines += [
                "### LambdaTest Credentials",
                "Required for HyperExecute parallel test execution.",
                "",
                "```bash",
                "# Find your credentials at: https://accounts.lambdatest.com/security",
                "export LT_USERNAME=your_username",
                "export LT_ACCESS_KEY=your_access_key",
                "```",
                "",
            ]

        lines += [
            "---",
            "",
            "Once credentials are set, re-run:",
            "```bash",
            "agentic-stlc chat --requirements requirements.txt --repo https://github.com/org/repo",
            "```",
        ]
        return "\n".join(lines)


class CredentialValidator:
    """Validates all pipeline credentials before execute() begins."""

    _GITHUB_URL_RE = re.compile(
        r"^https://github\.com/(?P<slug>[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+?)(?:\.git)?/?$"
    )

    def validate(self, repo_url: str = "") -> CredentialReport:
        report = CredentialReport()

        self._check_github_token(report)
        self._check_lt_credentials(report)
        self._check_repo_url(report, repo_url)

        return report

    # ── Internal checks ───────────────────────────────────────────────────────

    def _check_github_token(self, report: CredentialReport) -> None:
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            report.errors.append(
                "GITHUB_TOKEN is not set. Cannot push generated files or trigger CI pipeline."
            )
            return

        report.github_token = True
        # Verify the token actually works via GitHub API
        try:
            import httpx
            resp = httpx.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                scopes = resp.headers.get("x-oauth-scopes", "")
                report.github_token_scope = scopes or "unknown"
                if "repo" not in scopes and "workflow" not in scopes:
                    report.warnings.append(
                        f"GITHUB_TOKEN has limited scopes ({scopes!r}). "
                        "Ensure 'repo' and 'workflow' scopes are granted for push + CI trigger."
                    )
            elif resp.status_code == 401:
                report.github_token = False
                report.errors.append(
                    "GITHUB_TOKEN is invalid or expired (401). Generate a new token at "
                    "https://github.com/settings/tokens with 'repo' and 'workflow' scopes."
                )
            else:
                report.warnings.append(
                    f"GitHub API returned {resp.status_code} when verifying GITHUB_TOKEN. "
                    "Token may have limited access."
                )
        except Exception as exc:
            report.warnings.append(f"Could not verify GITHUB_TOKEN via API: {exc}")

    def _check_lt_credentials(self, report: CredentialReport) -> None:
        username = os.environ.get("LT_USERNAME", "").strip()
        access_key = os.environ.get("LT_ACCESS_KEY", "").strip()

        if not username:
            report.errors.append(
                "LT_USERNAME is not set. Required for HyperExecute parallel execution."
            )
        else:
            report.lt_username = True

        if not access_key:
            report.errors.append(
                "LT_ACCESS_KEY is not set. Required for HyperExecute parallel execution."
            )
        else:
            report.lt_access_key = True

        if report.lt_username and report.lt_access_key:
            # Light verification: ping the LambdaTest API
            try:
                import httpx
                import base64
                creds = base64.b64encode(f"{username}:{access_key}".encode()).decode()
                resp = httpx.get(
                    "https://api.lambdatest.com/automation/api/v1/builds",
                    headers={"Authorization": f"Basic {creds}"},
                    params={"limit": 1},
                    timeout=10,
                )
                if resp.status_code == 200:
                    report.lt_credentials_valid = True
                elif resp.status_code in (401, 403):
                    report.lt_credentials_valid = False
                    report.errors.append(
                        "LT_USERNAME / LT_ACCESS_KEY are invalid (401/403). "
                        "Check your credentials at https://accounts.lambdatest.com/security"
                    )
                else:
                    report.warnings.append(
                        f"LambdaTest API returned {resp.status_code} during credential check."
                    )
            except Exception as exc:
                report.warnings.append(f"Could not verify LambdaTest credentials via API: {exc}")

    def _check_repo_url(self, report: CredentialReport, repo_url: str) -> None:
        url = (repo_url or "").strip()
        if not url:
            report.errors.append(
                "Repository URL is not set. Provide --repo https://github.com/org/repo "
                "or set project.repository in agentic-stlc.config.yaml"
            )
            return

        m = self._GITHUB_URL_RE.match(url)
        if not m:
            report.errors.append(
                f"Repository URL '{url}' does not look like a valid GitHub URL. "
                "Expected: https://github.com/owner/repo"
            )
            return

        report.repo_url = True
        report.repo_slug = m.group("slug")

# Security Policy

## Supported Versions

Simposter doesn't publish tagged/versioned releases — images on [ghcr.io/pjgithub9/simposter](https://github.com/PJGithub9/Simposter/pkgs/container/simposter) are built continuously per-branch, and `latest` tracks whatever's on `main`. Only the latest code on `main` (or the `latest` image) is supported. If you're running an older commit or an image pinned to an older branch tag, please update before reporting a security issue.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting: go to the **Security** tab → **Report a vulnerability**. This opens a private advisory that's only visible to the maintainer, so the issue isn't public until it's fixed.

This is a solo-maintained hobby project, not a funded security team — please expect a response measured in days, not hours.

## Scope

Simposter is a **self-hosted, single-user-oriented app with no built-in authentication** — this is a deliberate design choice for a self-hosted homelab tool, not an oversight. Anyone who can reach the configured port has full read/write access to the API. If you're exposing Simposter beyond your local network, put it behind a reverse proxy with your own authentication layer (e.g. Authelia, Tailscale, basic auth) — Simposter is not designed to be safely exposed without one.

Given that, **"there's no login screen" isn't a vulnerability report** — it's a known tradeoff. What is genuinely in scope:

- Anything that goes *beyond* what the trusted-network model already assumes — e.g. reading/writing files outside the app's own directories, making the server issue requests to arbitrary internal or external hosts (SSRF), database injection, or bypassing the webhook secret check when one is configured
- Secrets (API keys, Plex tokens) being exposed in logs, API responses, or database exports when they shouldn't be
- A dependency vulnerability in `requirements.txt` / `frontend/package.json` with an actual exploit path through how Simposter uses it — Dependabot already flags version bumps on its own, so there's no need to report those individually unless there's a specific exploit concern

Thanks for helping keep Simposter and its users safe.

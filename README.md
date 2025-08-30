# .github

# Nova Org Automation (.github)

This repository provides an org-wide reusable workflow: "Org CI + Security (Required)".

What it does on each PR:
- Auto-detects languages (Node, Python, Go, Java/Maven/Gradle, Rust, .NET, Ruby).
- Lints with Super-Linter.
- Builds and runs tests per language.
- Code scanning (CodeQL) for supported languages.
- Vulnerability/secret/misconfig scans (Trivy) and SBOM artifact.
- Generates an autofixes.patch with safe formatter/linter fixes and (on PRs) comments with how to apply.

Enable as an Organization Required Workflow (applies to all repos, including future)
1) Organization Settings → Actions → Required workflows → New required workflow.
2) Select this repo (Nova-s-Personal-Organization/.github) and pick: Org CI + Security (Required).
3) Apply to All repositories and include future repositories.
4) Create a Repository rule (branch protection) requiring this check to pass on your default branches.

Recommended org-wide security
- Settings → Code security and analysis:
  - Code scanning default setup: Enable for all repos + future repos.
  - Secret scanning + Push protection: Enable for all repos.
  - Dependabot alerts and (optional) security updates: Enable org-wide.

Optional: run on push/schedule in each repo
Required workflows trigger on PRs. If you also want runs on push/nightly, add the wrapper below to each repo at .github/workflows/ci.yml:

```yaml
name: CI + Security (Org)

on:
  push:
  pull_request:
  merge_group:
  schedule:
    - cron: '17 3 * * *' # daily 03:17 UTC
  workflow_dispatch:

permissions:
  contents: read
  security-events: write
  checks: write
  actions: read
  pull-requests: write
  issues: write

jobs:
  org_ci:
    uses: Nova-s-Personal-Organization/.github/.github/workflows/org-ci-required.yml@main
    secrets: inherit
```

Dependabot template (optional, add to repos you want managed)

```yaml
version: 2
updates:
  - package-ecosystem: npm
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: pip
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: gomod
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: maven
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: gradle
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: cargo
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: nuget
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: bundler
    directory: "/"
    schedule: { interval: weekly }
```

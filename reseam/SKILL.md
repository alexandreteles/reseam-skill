---
name: reseam
description: Use Reseam to work with patch bundles, its CLI, or its HTTP API. Find current or release-specific documentation and manage a user-local CLI and Java runtime when needed.
---

# Reseam

On the first Reseam request in a session, run `python3.14 <skill>/scripts/docs.py sync --refresh` from the user's working directory. Replace `<skill>` with the directory containing this file. On later requests, use `sync`. It checks again after 30 minutes. Force a check when the user asks for the latest information or wants to install or update the CLI.

Use the returned `docs_root` to browse or search the full collection. `catalog_path` gives the Markdown catalog. Keep the same root and CLI version through each task. For a project with a pinned Reseam version, use its matching guide. [Documentation lookup](references/docs.md)

When a CLI is present, compare its version with `latest_cli` from a successful check. Offer a newer stable release once. When a task needs a missing CLI, offer to install it. An explicit request for the selected version and install method gives approval. Otherwise ask before changing tools. [CLI installation and updates](references/cli-install.md)

If the platform has no published binary, offer a build from the release tag. If patching or building needs Java, check for a suitable runtime or JDK and offer a private installation. [Source builds](references/cli-build.md) · [Java setup](references/java.md)

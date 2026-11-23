# CLI installation and updates

## Find the installed CLI

Use `cache_root` from the documentation helper. For skill-managed binaries, use `cli/<os>-<arch>/` below that root. Use the host OS and CPU, for example `linux-x64`, `windows-x64`, or `macos-aarch64`. The `active` text file in that directory contains the selected release tag. Resolve the executable as `<tag>/reseam` or `<tag>/reseam.exe`. Otherwise use the existing executable on `PATH`. Run its absolute path with `--version`.

Compare release versions numerically, including prerelease precedence. A leading `v` on a tag is optional. Honor a project pin. When a newer stable version is available, show the current version, proposed version, method, and destination. For automatic offers, remember the last tag offered in `cli/<os>-<arch>/last-offered`. An explicit request can revisit a declined version. A documentation question can proceed with the local manuals alone.

## Install an approved release

1. Run `docs.py sync --refresh`. Select the approved tag from `reseam/reseam`. Read the install guide at that tag using [documentation lookup](docs.md). If another release appears during installation, finish with the approved tag.
2. Match the operating system and CPU to a published CLI binary. The CLI section of the official download page links to its CDN. Check the tag in that link because the website is built separately. The GitHub release API at `https://api.github.com/repos/Reseam/reseam/releases/tags/<tag>` also supplies asset names, `browser_download_url`, and published `digest` values. Use a matching asset from the same tag. If no binary fits, offer a [source build](cli-build.md). [Official downloads](https://reseam.app/download/) · [Release mirror](https://github.com/Reseam/reseam/releases)
3. Stage the binary in a new private directory on the same filesystem as its destination. On POSIX, `mktemp -d "$platform_dir/.install.XXXXXXXX"` creates that directory under the private platform directory. Verify the published checksum when available. Give the staged executable its final name and user execute permission. Run it with `--version` and compare the result with the approved tag.
4. Rename the verified directory to `cli/<os>-<arch>/<tag>/`. If it already exists, verify and reuse its binary. Write the tag to a temporary text file and atomically replace `active`. Later calls use the selected binary by absolute path. A failed download, checksum, or version check ends the attempt before activation.

For all tool writes, use private directories under the helper's recognized cache. Check each destination component for links or Windows junctions. Use a tag as a directory name only if it is a single portable filename. Keep existing installations managed by the user or a package manager under their existing ownership. Clean up only the staging directory created for this operation.

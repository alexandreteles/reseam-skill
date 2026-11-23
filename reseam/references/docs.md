# Documentation lookup

Run the Python 3.14 helper from the project, using the absolute path to this skill's `scripts/docs.py`. On Windows, `py -3.14` selects that interpreter.

| Command argument | Result |
| --- | --- |
| `sync --refresh` | Check both repository heads and the stable CLI release now. Use this on first use in a session. |
| `sync` | Use the cached results until the next check is due. |
| `status` | Read the last complete snapshot offline. |

The JSON output gives absolute paths in `docs_root` and `catalog_path`. `checked` and `release_checked` give the last successful checks in UTC. A network failure is reported on stderr. When using a cached answer after a failure, give the relevant check time. If there is no local copy, the helper exits with an error. The published site can still serve individual pages. [Reseam documentation](https://reseam.app/docs/)

## Find a section

The catalog lists filenames in numeric order with page titles, descriptions, headings, and links to the exact revision. The agent can also use its normal file tools anywhere under `docs_root`. The following paths are relative to that root.

| Subject | Directory |
| --- | --- |
| Writing Kotlin patches, the patch API, Gradle, engine internals | `reseam/docs/` |
| CLI commands, flags, binaries, and device operations | `reseam/crates/cli/docs/` |
| HTTP endpoints and running the API server | `api/docs/` |

For example, `rg -n -F -- 'JAVA_HOME' "$docs_root"` finds each occurrence with a line number. Open the matching section and read the example in context. Use the catalog's source link when citing a page.

## Match the version

The two commits in `commits` identify the snapshot. A later sync can publish another snapshot while the current task continues to use its original paths. Forgejo is the primary source. GitHub can serve files at the same commit. During an outage, the helper checks that a new mirror head includes the cached commit.

For a pinned project or an older CLI, look up the relevant folder at the installed release tag. For example, request `https://git.reseam.app/api/v1/repos/reseam/reseam/contents/crates/cli/docs?ref=<tag>` and open the install or command page using its `download_url`. The mirror provides the same listing at `https://api.github.com/repos/Reseam/reseam/contents/crates/cli/docs?ref=<tag>`. URL-encode the tag. Check flags against the installed executable's `--help`. If a release has no tagged manual, identify that gap when using a newer page.

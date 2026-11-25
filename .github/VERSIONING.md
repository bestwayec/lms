# Versioning rule — SemVer

Single source of truth: root `VERSION` file.
Every release version is baked into that release's commit, git tag `vX.Y.Z`, GitHub Release, and Docker image (`:sha-<commit>`, `:vX.Y.Z`, `:latest`), so `/healthz/` always matches the GitHub Release.

## Format: MAJOR.MINOR.PATCH

| Part  | When to bump | Example |
| ----- | ------------ | ------- |
| MINOR | **Every code update to `main`** (automatic) | `2.9.0` → `2.10.0` |
| PATCH | Hotfix without new features (manual dispatch) | `2.10.0` → `2.10.1` |
| MAJOR | Breaking / major milestone (manual dispatch) | `2.10.0` → `3.0.0` |

## Pipeline order (no PAT needed, zero loops)

1. Merge PR to `main` → **CI** + **Security** run on source commit `C`.
2. When **CI** succeeds on `main`, **Release** runs (`workflow_run: [CI]`):
   - Updates `VERSION` to `NEXT`, commits `chore(release): vX.Y.Z [skip ci]` (`R`),
   - Creates annotated tag `vX.Y.Z` **on `R`** (so `vX.Y.Z` and `VERSION` match identically),
   - Creates GitHub Release `vX.Y.Z` targeting `R`, and uploads `release-meta`.
3. When **Release** succeeds, **Build** runs (`workflow_run: [Release]`):
   - Verifies `R`'s parent `C` passed **CI** and only `VERSION` changed between `C` and `R`,
   - Asserts `VERSION == build APP_VERSION`,
   - Builds & pushes `ghcr.io/bestwayec/lms:sha-<short_R>`, `:vX.Y.Z`, and `:latest` with provenance attestation,
   - Verifies manifest digest via `docker buildx imagetools inspect` and uploads `build-meta`.
4. **Deploy** (`workflow_run: [Build]`):
   - **Staging**: automatic when `STAGING_HOST` and `STAGING_DOMAIN` secrets are configured in the `staging` environment (skips cleanly otherwise).
   - **Production**: **manual only** (`Actions → Deploy → Run workflow`, enter immutable `sha-<short_R>` tag and confirmation phrase `deploy grandec.uz`).
5. **Loop prevention**: release commits include `[skip ci]`, `GITHUB_TOKEN` pushes do not trigger `push` workflows, and `Release` skips any `chore(release):` head commit.

## Rules

- Never edit `VERSION` by hand in feature PRs — `Release` owns it.
- Never create release tags by hand — use `Release` so git tag, GitHub Release, `VERSION`, and Docker image remain 1:1.

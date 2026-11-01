# Releasing

A maintainer cuts a release in four steps. `release.yml` does the rest.

Do not cut a release before PrivacyFence 7.0.0 is out: the suite floats on PrivacyFence's `latest`, and before 7.0.0 that is a version the suite does not work with.

1. **CHANGELOG.** In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and add a new empty `## [Unreleased]` above it. Say if an image tag changed, and which files the release drops (the upgrade leaves them in place). `release.yml` publishes this section as the release notes and fails if it is empty.
2. **Merge to `main`.** The tag's commit must be on `origin/main`; the workflow refuses it otherwise.
3. **Tag `main` and push the tag:**

   ```sh
   git checkout main && git pull
   git tag -a vX.Y.Z -m vX.Y.Z
   git push origin vX.Y.Z
   ```

4. **Wait for the `release` workflow.** It checks the tag and the changelog section, runs `pytest`, `check_configs.py` and `ruff`, builds the assets with `scripts/build_release.sh`, attests build provenance, and creates the GitHub release with:
   - `privacyfence-suite-<config>.tar.gz` and `.zip` for each configuration;
   - `install.sh`, stamped with the version;
   - `SHA256SUMS`.

A `-` in the version (`v0.2.0-rc1`) makes a pre-release. `releases/latest` skips pre-releases, so the one-liner keeps installing the last full release; install a pre-release by its tag: `.../releases/download/v0.2.0-rc1/install.sh`.

**Check the result** on a machine without the repository:

```sh
curl -fsSL https://github.com/privacyfence/privacyfence-suite/releases/latest/download/install.sh | sh -s -- localhost --dir /tmp/pf-check
cat /tmp/pf-check/VERSION
sha256sum -c --ignore-missing SHA256SUMS   # after downloading SHA256SUMS and an archive
gh attestation verify privacyfence-suite-localhost.tar.gz --repo privacyfence/privacyfence-suite
```

`VERSION` must show `X.Y.Z`. To try the build without a release, run `sh scripts/build_release.sh 0.0.0-test dist`; `ci.yml` does the same on every push.

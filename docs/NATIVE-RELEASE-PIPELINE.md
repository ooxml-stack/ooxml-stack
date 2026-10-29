# Native release pipeline

The native release pipeline is fail-closed. A public release is not a development artifact and cannot use ad-hoc signatures, staged licenses, mutable page metadata, or implicit candidate selection.

## Commands

```bash
make native-dev
make native-test CANDIDATE=/absolute/path/to/OOXML-macos-arm64.dmg INTERNAL_LICENSE=1
make native-test CANDIDATE=/absolute/path/to/OOXML-macos-arm64.dmg
make native-wheelhouse NATIVE_WHEELHOUSE=/absolute/path/to/empty-wheelhouse
make native-release-local
make native-release
.venv-ecosystem-inventory/bin/python -m scripts.native_release verify-live
```

`native-dev` permits ad-hoc signing and is never publishable. `native-test` requires an explicit candidate; `CANDIDATE=latest-dev` is a local-only shortcut. `native-wheelhouse` refuses dirty source trees, builds third-party and first-party wheels, and writes the committed wheelhouse lock. `native-release-local` requires clean repositories, Developer ID signing, notarization, and a valid external release-test license, but skips the external publish transaction. `native-release` adds the configured publish adapter and requires `OOXML_NATIVE_RELEASE_COMMIT`.

## Required environment

- `OOXML_NATIVE_DEVELOPER_ID_APPLICATION`: full Developer ID Application identity.
- `OOXML_NATIVE_NOTARY_PROFILE`: notarytool keychain profile.
- `OOXML_NATIVE_E2E_LICENSE`: external test entitlement; its body is never copied into evidence.
- `OOXML_NATIVE_E2E_WORD`, `OOXML_NATIVE_E2E_EXCEL`, `OOXML_NATIVE_E2E_PPTX`: external acceptance fixtures.
- `OOXML_NATIVE_WHEELHOUSE`: frozen wheel directory. Release requires the exact pinned Nuitka and runtime wheels.
- `OOXML_NATIVE_BUILD_ENV`: optional reusable build environment for local development only; release rejects it.
- `OOXML_NATIVE_PUBLISH_STEP_COMMAND`: executes one approved publish transaction step at a time. The implemented adapter is `python -m scripts.native_release.publish_github_release`.
- `OOXML_NATIVE_RELEASE_COMMIT`: required full SHA of the pushed release commit for public publication. Local-only release derives its commit from the clean stack checkout instead.
- `OOXML_NATIVE_RELEASE_TAG`: optional explicit immutable GitHub release tag; otherwise derived from the versioned artifact URL.
- `OOXML_NATIVE_GITHUB_REPO`: optional repository override, defaulting to `ooxml-stack/ooxml-stack`.

## Contract

The profile is `release/native-macos-arm64.yaml`.

- The distribution is a standalone directory with embedded CPython.
- DMG is the page-visible artifact and is signed, notarized, and stapled.
- ZIP is the automation artifact. It is notarized online but cannot be stapled.
- Public page and automation URLs use immutable versioned artifact paths.
- `latest` is an independent alias and is updated after versioned verification.
- The release-test license must be signed, current, artifact-matched, and not a staging/internal entitlement.
- Public artifacts are scanned after signature and DMG/zip construction, not merely at an intermediate stage.
- CPython/toolchain strings are accepted only through the reviewed allowlist in `release/native-scan-allowlist.json`.
- Build attestations distinguish pre-sign payload, normalized signed payload, and container hashes.

## Publish transaction

```text
artifact:dmg
checksum:dmg
artifact:zip
checksum:zip
manifest:versioned
page:update
verify:versioned
latest:update
verify:latest
```

The product page never consumes `latest` for displayed hash or size. This avoids a window where the page advertises a new hash while the alias still resolves to the previous artifact.

`page:update` uploads `page-metadata.json` but does not claim to mutate the static Vercel page. Live verification requires the deployed page to declare mode `manifest-v1` in `<meta name="ooxml-native-release-mode" content="manifest-v1">` and to reference the configured latest manifest URL. Missing declarations fail the transaction with an explicit page blocker before `latest` changes.

Release evidence is sealed before external publication. After publication, a separate post-publish receipt records the completed transaction steps without resealing the directory.

## Current implementation boundary

The Nuitka source-to-stage builder is now in this repository. `native-dev` permits a reusable build environment and ad-hoc signing, but its output is DEV_ONLY. Internal candidate tests can explicitly accept the staging license with `INTERNAL_LICENSE=1`; public release validation rejects it. Fly publication and product-page mutation remain behind the step adapter until the delivery service is migrated to versioned storage/routes.

The current machine has no Developer ID Application identity, so `make native-release` must fail before signing. That is the intended behavior, not a release failure workaround.
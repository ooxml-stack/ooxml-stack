# Native release pipeline

The native release pipeline is fail-closed. A public release is not a development artifact and cannot use ad-hoc signatures, staged licenses, mutable page metadata, or implicit candidate selection.

## Commands

```bash
make native-dev
make native-test CANDIDATE=/absolute/path/to/OOXML-macos-arm64.dmg
make native-release
```

`native-dev` permits ad-hoc signing and is never publishable. `native-test` requires an explicit candidate; `CANDIDATE=latest-dev` is a local-only shortcut. `native-release` requires clean repositories, Developer ID signing, notarization, a valid external release-test license, and the configured publish adapter.

## Required environment

- `DEVELOPER_ID_APPLICATION`: full Developer ID Application identity.
- `NOTARY_PROFILE`: notarytool keychain profile.
- `OOXML_E2E_LICENSE`: external test entitlement; its body is never copied into evidence.
- `OOXML_NATIVE_BUILD_COMMAND`: build adapter used until the Nuitka builder is migrated into this repository.
- `OOXML_NATIVE_PUBLISH_STEP_COMMAND`: executes one approved publish transaction step at a time.

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

## Current implementation boundary

This change establishes the configuration and control-plane gates. It intentionally does not fall back to ad-hoc signing or the current staging license. The Nuitka build and Fly publication remain external adapters until their source-specific migration is complete.

The current machine has no Developer ID Application identity, so `make native-release` must fail before signing. That is the intended behavior, not a release failure workaround.

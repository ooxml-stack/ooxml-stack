# OOXML macOS arm64 release

This is a mixed native package with an embedded CPython runtime. It does not require a separately installed Python runtime.

Verify the DMG or ZIP with the checksum sidecar before installation. The DMG is a signed and notarized installer container: open it and run Install.command. The script verifies the embedded ZIP SHA-256 and expands the complete OOXML runtime to ~/.local/ooxml by default. The standalone ZIP contains the same runtime with its top-level OOXML directory. Keep bin, lib, and docs together; copying only the two launchers is unsupported.

Activation requires an entitlement supplied through the public activation channel. The archive contains only the public verification key. A missing or invalid license fails closed.

MCP core exposes 8 tools. MCP workflow exposes 10 tools. File rendering still depends on the selected external Office or LibreOffice provider.

Uninstall by removing the installed OOXML directory and the user activation file. Agent-owned MCP registrations must be removed through the agent application.

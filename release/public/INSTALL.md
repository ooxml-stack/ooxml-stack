# OOXML macOS arm64 release

This is a mixed native package with an embedded CPython runtime. It does not require a separately installed Python runtime.

Verify the DMG or ZIP with the checksum sidecar before installation. Open the DMG, move the complete OOXML directory to a user-owned location, and add its bin directory to PATH. Keep bin, lib, and docs together; copying only the two launchers is unsupported.

Activation requires an entitlement supplied through the public activation channel. The archive contains only the public verification key. A missing or invalid license fails closed.

MCP core exposes 8 tools. MCP workflow exposes 10 tools. File rendering still depends on the selected external Office or LibreOffice provider.

Uninstall by removing the installed OOXML directory and the user activation file. Agent-owned MCP registrations must be removed through the agent application.

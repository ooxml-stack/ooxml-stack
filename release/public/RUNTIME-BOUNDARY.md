# Runtime boundary

Classification: mixed native package with an embedded CPython runtime.

Nuitka compiles the existing business logic ahead of time. The standalone directory still contains CPython and Python ABI extension libraries, so this is not a fully native or Python-runtime-free package.

Optional PyMuPDF/fitz PDF readability verification is excluded. The runtime must return the stable error pdf_readability_unavailable rather than exposing an import error. Required editing, validation, MCP, activation, status, and Skill paths do not depend on this optional check.

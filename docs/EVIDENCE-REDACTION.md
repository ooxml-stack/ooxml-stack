# Evidence and log redaction policy

Committed evidence, reports and logs must not carry credentials, personal data or
content copied out of a user's document. `scripts/check_evidence_redaction.py`
enforces the first rule and measures the third.

## Never commit

| Class | Examples | What to write instead |
| --- | --- | --- |
| Credentials | GitHub tokens (`ghp_…`, `github_pat_…`), `x-access-token:` headers, `-----BEGIN … PRIVATE KEY-----` blocks, AWS access key ids | an environment placeholder such as `${{ secrets.OOXML_STACK_TOKEN }}` |
| Personal data | names, e-mail addresses, machine hostnames in receipts | the role, not the person (`the release operator`) |
| Document content | text, cells or images lifted from a customer document | a size or hash, or a synthetic fixture the repository owns |
| Absolute home paths | `/Users/<name>/…`, `/home/<name>/…` | a workspace-relative path, `${WORKSPACE}/…`, or `${TMPDIR}` |

## Enforcement

```bash
python3 scripts/check_evidence_redaction.py
```

- **Hard failure** on the credential patterns above. A match means removing the
  value *and rotating it*: the commit history still contains it.
- **Reported, not blocking**: absolute home-path counts. These leak a local
  username and make evidence non-portable, but they are historical; the count is
  expected to fall as files are touched.

## Current state

- Evidence files scanned: 936
- Credential patterns: none
- Absolute home paths: 64 occurrences in 16 files (tracked for sanitisation; new files must not add any)

## Where evidence belongs

Generated evidence lives outside the source checkout (see `docs/ARTIFACT-STORAGE.md`
where present, and the workspace rules). A path inside the repository is a
decision that has to be justified in the pull request; `reports/runs/<id>/` style
trees are normally ignored rather than committed.

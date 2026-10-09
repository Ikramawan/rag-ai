# Synthetic corpus expansion

The generator adds 22 fictional training documents to the original eight-document
local corpus. Every generated document explicitly states that it is synthetic and
is not company policy. No credentials, company data or real infrastructure
destinations are included.

## Generate documents

Install development dependencies in the project virtual environment:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m scripts.generate_synthetic_corpus --output data/documents/synthetic-v2
```

The output directory is explicit. Existing target filenames cause the entire run
to abort before generation. Files are staged and checked for extractable synthetic
notices before publication; failed publication removes only files created by that
run. Other documents are left alone. Running the command again refuses to overwrite
the generated corpus. Generated documents remain excluded from Git; their source
definitions are versioned in the generator.

## Coverage

| Format | Count | Representative coverage |
|---|---:|---|
| Markdown | 12 | GCP labels, billing alerts, API/quota requests, access prerequisites, release evidence, rollback review, certificate triage, exposed-secret reporting, data access/export |
| Text | 3 | MFA clock mismatch, incident notifications, maintenance timezones |
| HTML | 3 | Application roles, backup retention and certificate routing tables |
| Word | 2 | Incident handoff and storage-access tables between prose sections |
| PDF | 2 | Deployment prerequisites and diagnostic redaction |

The release checklist contains a long ordered procedure to exercise multi-chunk
ingestion. Related topics provide retrieval distractors without changing the
original support response targets. Harbor is a fictional application used to scope
the new example rules. GCP project deletion and annual-leave policy remain absent.

## Validate without replacing the active index

```sh
.venv/bin/python -m pytest -q tests/test_synthetic_corpus.py
```

These tests generate temporary documents, use real extraction and chunking, and
fake embeddings to verify index integrity. They do not prove retrieval ranking,
answer correctness or citation grounding. The active local index must be rebuilt
explicitly to include the new documents; adding files alone does not activate them.

Content generation is reproducible; binary file bytes may vary because of archive
timestamps and PDF metadata. Complex PDF tables, merged/nested tables and Word
automatic numbering are not certified by these fixtures. Adversarial documents,
ambiguous evidence and reviewed questions belong to the next evaluation section.

PDF generation uses ReportLab; PDFium is available for local render checks.
Word visual checks require LibreOffice and a DOCX rendering tool. Extraction and
structural checks are useful but do not establish visual layout fidelity.

import requests

from app.search_documents import search

CASES = [
    (
        "What do I need before connecting to the VPN?",
        {
            "vpn-guide.docx": "Obtain an approved VPN account and enable MFA.",
            "vpn-account-access.md": "Enrol in MFA before the first connection.",
        },
        "",
    ),
    (
        "What should I do if self-service password reset fails?",
        "password-reset.html",
        "contact the service desk",
    ),
    (
        "What do I need before creating a GCP project?",
        "gcp-project-guide.md",
        "Obtain approval from the platform team.",
    ),
    (
        "When is the service desk available?",
        "support-hours.txt",
        "09:00–17:00 UK time",
    ),
    (
        "VPN is connected but two internal hostnames fail. What should I do?",
        "vpn-troubleshooting.md",
        "collect the VPN diagnostic bundle",
    ),
    (
        "VPN sign-in says Account locked. Who should I contact?",
        "vpn-account-access.md",
        "contact the identity support team",
    ),
    (
        "What is the P2 initial response target?",
        "support-priority-matrix.md",
        "1 business hour",
    ),
    (
        "My existing GCP project's billing account is suspended. What should I do?",
        "gcp-billing-troubleshooting.md",
        "contact the billing administrator",
    ),
    (
        "Which approval and billing details are needed to start a new GCP project?",
        "gcp-project-guide.md",
        "permission to link it",
    ),
    (
        "Who handles a VPN account that is locked when I sign in?",
        "vpn-account-access.md",
        "identity support team",
    ),
    (
        "Which labels must our GCP training project have?",
        "synthetic-v2/gcp-labels.md",
        "owner, environment and cost-centre",
    ),
    (
        "Do GCP budget alerts automatically stop spending?",
        "synthetic-v2/budget-alerts.md",
        "do not automatically stop spending",
    ),
    (
        "What evidence should I include in a GCP quota increase request?",
        "synthetic-v2/quota-request.md",
        "current quota, requested quota",
    ),
    (
        "What must I prepare before requesting database reporting-reader access?",
        "synthetic-v2/database-read-access.md",
        "approval from the data owner",
    ),
    (
        "How long are Harbor daily snapshot backups retained?",
        "synthetic-v2/backup-retention.html",
        "Daily snapshot | 14 days",
    ),
    (
        "What can a Harbor Viewer do, and who approves the role?",
        "synthetic-v2/harbor-roles.html",
        "Viewer | Read release records | Application owner",
    ),
    (
        "How long does storage Report reader access last?",
        "synthetic-v2/storage-access.docx",
        "Report reader | Read approved reports | 30 days",
    ),
    (
        "What are the prerequisites for scheduling a Harbor deployment?",
        "synthetic-v2/deployment-prerequisites.pdf",
        "reviewed rollback criteria",
    ),
    (
        "What is the final approval step in the release evidence checklist?",
        "synthetic-v2/release-evidence.md",
        "Wait for explicit approval",
    ),
    (
        "Which sensitive items must I redact from diagnostic screenshots?",
        "synthetic-v2/diagnostic-redaction.pdf",
        "MFA recovery codes",
    ),
]


def evaluate(*, cases=None, search_fn=None) -> dict:
    cases = CASES if cases is None else cases
    search_fn = search if search_fn is None else search_fn
    first_passed = 0
    top_three_passed = 0
    records = []

    for question, expected_source, expected_text in cases:
        accepted = (
            expected_source
            if isinstance(expected_source, dict)
            else {expected_source: expected_text}
        )
        try:
            results = search_fn(question, top_k=3)
            error = None
        except (OSError, ValueError, KeyError, requests.RequestException) as exc:
            results = []
            error = str(exc)

        matches = []
        for result in results:
            phrase = accepted.get(result["source"])
            matches.append(
                phrase is not None
                and " ".join(phrase.casefold().split())
                in " ".join(result["text"].casefold().split())
            )

        first_correct = bool(matches) and matches[0]
        evidence_found = any(matches)

        first_passed += int(first_correct)
        top_three_passed += int(evidence_found)

        first_status = "PASS" if first_correct else "FAIL"
        top_three_status = "PASS" if evidence_found else "FAIL"

        print(f"\n{question}")
        print(f"  First result: {first_status}")
        print(f"  Evidence in top three: {top_three_status}")
        if not first_correct:
            for result in results:
                print(f"  Retrieved: {result['source']} ({result['chunk_id']})")
        if error:
            print(f"  Error: {error}")
        records.append(
            {
                "question": question,
                "expected_evidence": accepted,
                "first_correct": first_correct,
                "evidence_found": evidence_found,
                "results": results,
                "error": error,
            }
        )

    total = len(cases)
    print(f"\nFirst-result checks: {first_passed}/{total}")
    print(f"Evidence-in-top-three checks: {top_three_passed}/{total}")

    return {
        "total": total,
        "first_passed": first_passed,
        "top_three_passed": top_three_passed,
        "cases": records,
    }


def main() -> None:
    report = evaluate()
    if report["top_three_passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

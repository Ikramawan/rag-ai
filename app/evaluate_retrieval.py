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
]


def main() -> None:
    first_passed = 0
    top_three_passed = 0

    for question, expected_source, expected_text in CASES:
        results = search(question, top_k=3)

        accepted = (
            expected_source
            if isinstance(expected_source, dict)
            else {expected_source: expected_text}
        )

        matches = []
        for result in results:
            phrase = accepted.get(result["source"])
            matches.append(
                phrase is not None and phrase.casefold() in result["text"].casefold()
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

    total = len(CASES)
    print(f"\nFirst-result checks: {first_passed}/{total}")
    print(f"Evidence-in-top-three checks: {top_three_passed}/{total}")

    if top_three_passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

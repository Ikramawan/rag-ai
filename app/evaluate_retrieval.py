from app.search_documents import search

CASES = [
    (
        "What do I need before connecting to the VPN?",
        "vpn-guide.docx",
        "Obtain an approved VPN account and enable MFA.",
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
]


def main() -> None:
    passed = 0

    for question, expected_source, expected_text in CASES:
        result = search(question, top_k=3)[0]

        correct = (
            result["source"] == expected_source
            and expected_text.casefold() in result["text"].casefold()
        )

        if correct:
            passed += 1

        status = "PASS" if correct else "FAIL"
        print(f"{status}: {question}")
        print(f"  First result: {result['chunk_id']}")

    print(f"\nPassed {passed}/{len(CASES)} retrieval checks.")

    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

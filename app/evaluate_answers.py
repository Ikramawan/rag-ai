import re

from app.answer_question import answer

CASES = [
    {
        "question": "What do I need before connecting to the VPN?",
        "required": ["approved", "VPN account", "MFA"],
        "forbidden": ["billing", "GCP", "project ID"],
        "citation": True,
    },
    {
        "question": "What should I do if self-service password reset fails?",
        "required": ["service desk"],
        "forbidden": ["billing", "GCP"],
        "citation": True,
    },
    {
        "question": "What do I need before creating a GCP project?",
        "required": [
            "approval",
            "platform team",
            "organisation",
            "folder",
            "unique project ID",
            "billing account",
            "permission",
        ],
        "forbidden": ["VPN"],
        "citation": True,
    },
    {
        "question": "When is the service desk available?",
        "required": ["Monday", "Friday", "09:00", "17:00", "UK"],
        "forbidden": ["24/7"],
        "citation": True,
    },
    {
        "question": "What is our procedure for deleting a GCP project?",
        "required": ["couldn't find enough information"],
        "forbidden": ["gcloud", "console", "click", "shut down"],
        "citation": False,
    },
]


def main() -> None:
    passed = 0

    for case in CASES:
        output = answer(case["question"])

        # Check the answer body, excluding the appended source list.
        body = output.split("\n\nRetrieved sources:", maxsplit=1)[0]
        normalized = body.casefold()

        problems = [
            f"Missing: {phrase}"
            for phrase in case["required"]
            if phrase.casefold() not in normalized
        ]
        problems.extend(
            f"Unexpected: {phrase}"
            for phrase in case["forbidden"]
            if phrase.casefold() in normalized
        )

        if case["citation"] and not re.search(r"\[\d+\]", body):
            problems.append("Missing citation")

        if not problems:
            passed += 1

        status = "FAIL" if problems else "PASS"
        print(f"\n{status}: {case['question']}")
        print(body)

        for problem in problems:
            print(f"  {problem}")

    print(f"\nPassed {passed}/{len(CASES)} answer checks.")

    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

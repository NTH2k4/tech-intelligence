import argparse
import json

from pathlib import Path

from intelligence.scorer import IntelligenceScorer


def main():
    parser = argparse.ArgumentParser(
        description="Tech Intelligence AI Scoring"
    )

    parser.add_argument(
        "--input",
        default="/tmp/tech-intelligence-collector.json"
    )

    parser.add_argument(
        "--output",
        default="/tmp/tech-intelligence-scored.json"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be greater than 0")

    input_path = Path(args.input)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    data = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    articles = data.get("articles", [])

    if not articles:
        raise ValueError("No articles found")

    selected = articles[:args.limit]

    print("Initializing Intelligence Engine...")

    scorer = IntelligenceScorer()

    print(f"Scoring model: {scorer.gemini.model}")
    print(f"Input articles: {len(selected)}")

    scored = scorer.score_articles(selected)

    output = {
        "generated_at": data.get("generated_at"),
        "scoring_model": scorer.gemini.model,
        "input_count": len(selected),
        "scored_count": len(scored),
        "articles": scored
    }

    output_path = Path(args.output)

    output_path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("\n========== INTELLIGENCE REPORT ==========\n")

    for index, article in enumerate(scored[:10], 1):
        intelligence = article["intelligence"]

        print(f"{index}. {article['title']}")
        print(f"   Source: {article['source']}")
        print(f"   Category: {intelligence['category']}")
        print(f"   Priority: {article['score']}/100")
        print(f"   Relevance: {intelligence['relevance_score']}")
        print(f"   Impact: {intelligence['impact_score']}")
        print(f"   Novelty: {intelligence['novelty_score']}")
        print(f"   Authority: {intelligence['source_authority_score']}")
        print(f"   Recommendation: {article['recommendation']}")
        print(f"   Confidence: {intelligence['confidence']}")
        print(f"   Summary: {intelligence['summary_vi']}")
        print()

    summary = {
        "read": sum(
            a["recommendation"] == "read" for a in scored
        ),
        "monitor": sum(
            a["recommendation"] == "monitor" for a in scored
        ),
        "skip": sum(
            a["recommendation"] == "skip" for a in scored
        )
    }

    print("========== SELECTION SUMMARY ==========")
    print(json.dumps(summary, indent=2))
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()

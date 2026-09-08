"""Compare exact keyword search and enhanced retrieval on labeled catalog cases."""

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.retrieval.composition import build_search_services
from app.services.catalog_service import CatalogQuery
from app.settings import Settings, load_settings


def constraint_violations(result, query):
    violations = []
    for product in result.items:
        if query.category and product.category != query.category:
            violations.append("category")
        for sku in product.skus:
            if query.sku_name and query.sku_name.casefold() not in sku.name.casefold():
                violations.append("sku_name")
            if query.in_stock and sku.stock <= 0:
                violations.append("stock")
            price = Decimal(sku.price.amount_minor) / 100
            if query.min_price is not None and price < query.min_price:
                violations.append("min_price")
            if query.max_price is not None and price > query.max_price:
                violations.append("max_price")
    return violations


def summarize(rows):
    positive = [row for row in rows if row["expected"]]
    negative = [row for row in rows if not row["expected"]]
    recalls, reciprocal_ranks = [], []
    for row in positive:
        expected = set(row["expected"])
        recalls.append(len(expected & set(row["retrieved"])) / len(expected))
        reciprocal_ranks.append(next((1 / index for index, item in enumerate(row["retrieved"], 1)
                                     if item in expected), 0))
    return {"recall_at_k": sum(recalls) / len(recalls) if recalls else 0,
            "mrr_at_k": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0,
            "negative_accuracy": sum(not row["retrieved"] for row in negative) / len(negative) if negative else 1,
            "constraint_violations": sum(len(row["violations"]) for row in rows),
            "positive_cases": len(positive), "negative_cases": len(negative)}


async def evaluate(settings, dataset):
    services = build_search_services(settings)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "k": dataset["k"],
              "mode": "configured-embeddings" if settings.provider_configured("embedding") else "local-lexical-fallback",
              "reranker_requested": settings.provider_configured("reranker"), "variants": {}}
    for mode in ["keyword", "semantic"]:
        rows = []
        for case in dataset["cases"]:
            query = CatalogQuery(**case["query"], search_mode=mode, limit=dataset["k"])
            result = await services.products.search(query)
            rows.append({"id":case["id"], "expected":case["relevant_product_ids"],
                         "retrieved":[product.id for product in result.items],
                         "strategy":result.retrieval.strategy,
                         "fallback_reason":result.retrieval.fallback_reason,
                         "violations":constraint_violations(result, query)})
        report["variants"][mode] = {"metrics":summarize(rows), "cases":rows}
    return report


def check_report(report, gates):
    keyword = report["variants"]["keyword"]["metrics"]
    enhanced = report["variants"]["semantic"]["metrics"]
    checks = {"recall": enhanced["recall_at_k"] >= gates["min_recall"],
              "mrr": enhanced["mrr_at_k"] >= gates["min_mrr"],
              "negative_accuracy": enhanced["negative_accuracy"] >= gates["min_negative_accuracy"],
              "no_constraint_violations": enhanced["constraint_violations"] == keyword["constraint_violations"] == 0,
              "keyword_gain": enhanced["recall_at_k"] - keyword["recall_at_k"] >= gates["min_keyword_recall_gain"]}
    # A requested live run must actually use vector retrieval, not silently pass via fallback.
    if report["mode"] == "configured-embeddings":
        checks["live_vector_used"] = all(row["strategy"] in {"vector", "vector_rerank"}
                                        for row in report["variants"]["semantic"]["cases"]
                                        if row["expected"])
    if report.get("reranker_requested"):
        checks["live_reranker_used"] = all(row["strategy"] == "vector_rerank"
                                          for row in report["variants"]["semantic"]["cases"] if row["expected"])
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use configured embedding/rerank providers; consumes quota")
    parser.add_argument("--check", action="store_true", help="Exit unsuccessfully when a regression gate fails")
    parser.add_argument("--output", type=Path, default=ROOT / "data/retrieval-eval.json")
    args = parser.parse_args()
    settings = load_settings(ROOT / ".env") if args.live else Settings()
    if args.live and not settings.provider_configured("embedding"):
        parser.error("Configure EMBEDDING_BASE_URL, EMBEDDING_MODEL and its local key before --live.")
    dataset = json.loads((ROOT / "eval/catalog-cases.json").read_text(encoding="utf-8"))
    report = asyncio.run(evaluate(settings, dataset))
    report["checks"] = check_report(report, dataset["gates"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode":report["mode"], "k":report["k"],
                      "metrics":{name:result["metrics"] for name,result in report["variants"].items()},
                      "checks":report["checks"]}, ensure_ascii=False))
    if args.check and not all(report["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

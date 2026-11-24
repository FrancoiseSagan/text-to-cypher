"""Verify all 30 NL-Cypher knowledge base entries against the live Neo4j database."""
import json
import sys
from pathlib import Path
from neo4j import GraphDatabase

URI = "bolt://62.234.93.223:30005"
AUTH = ("neo4j", "admin123")


def main() -> int:
    kb_path = Path(__file__).resolve().parent.parent / "data" / "seed_kb.json"
    items = json.loads(kb_path.read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(URI, auth=AUTH)

    passed = 0
    failed = []
    categories: dict[str, int] = {}

    with driver.session() as session:
        for item in items:
            cat = item["category"]
            categories[cat] = categories.get(cat, 0) + 1
            qid = item["id"]
            cypher = item["cypher"]
            try:
                # 1. EXPLAIN check
                session.execute_read(lambda tx, q=cypher: tx.run(f"EXPLAIN {q}").consume())
                # 2. Live execution
                records = session.execute_read(lambda tx, q=cypher: list(tx.run(q)))
                if len(records) == 0:
                    failed.append((qid, item["question"], "EMPTY RESULT"))
                else:
                    passed += 1
                    print(f"[PASS] {qid} ({cat}/{item['complexity']}): {len(records)} rows - {item['question']}")
            except Exception as exc:
                failed.append((qid, item["question"], str(exc)))
                print(f"[FAIL] {qid}: {exc}")

    driver.close()
    print("\n=== SUMMARY ===")
    print(f"Total: {len(items)}, Passed: {passed}, Failed: {len(failed)}")
    print("Categories:", json.dumps(categories, ensure_ascii=False))
    if failed:
        print("Failures:")
        for f in failed:
            print(" ", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

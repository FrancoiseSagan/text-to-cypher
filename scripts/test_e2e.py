"""Comprehensive end-to-end verification of the FastAPI server, T1/T2/T3 capabilities, KB CRUD, Batch & Markdown export."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from backend.main import app


def main() -> int:
    client = TestClient(app)

    # 1. Health & Providers & Schema & Skills
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["neo4j_connected"] is True, r.text
    print("[PASS] /api/health:", r.json())

    r = client.get("/api/providers")
    assert r.status_code == 200
    pids = [p["id"] for p in r.json()["providers"]]
    assert set(pids) == {"deepseek", "glm", "kimi"}, f"Unexpected providers: {pids}"
    print("[PASS] /api/providers (strictly DeepSeek/GLM/Kimi):", pids, "default:", r.json()["default_provider"])

    r = client.get("/api/schema")
    assert r.status_code == 200
    schema = r.json()
    assert len(schema["active_labels"]) >= 8 and len(schema["triplets"]) > 0
    print(f"[PASS] /api/schema: {len(schema['active_labels'])} active labels, {len(schema['triplets'])} triplets")

    r = client.get("/api/skills")
    assert r.status_code == 200 and len(r.json()["skills"]) == 5
    print("[PASS] /api/skills:", [s["name"] for s in r.json()["skills"]])

    # 2. Knowledge Base CRUD & Live Verify (T2 + Req 8)
    r = client.get("/api/kb")
    assert r.status_code == 200 and r.json()["total"] >= 30
    print(f"[PASS] /api/kb list: {r.json()['total']} items across {len(r.json()['categories'])} categories")

    r = client.post("/api/kb/verify", json={"cypher": "MATCH (n) DELETE n"})
    assert r.status_code == 200 and r.json()["valid"] is False
    print("[PASS] /api/kb/verify blocked dangerous DELETE")

    r = client.post(
        "/api/kb",
        json={
            "question": "临时测试：统计微服务总数",
            "cypher": "MATCH (s:微服务) RETURN count(s) AS 总数",
            "category": "单节点查询",
            "complexity": "简单",
            "tags": ["测试"],
            "description": "自动化测试条目",
        },
    )
    assert r.status_code == 200 and r.json()["verified"] is True
    created_id = r.json()["id"]
    r = client.delete(f"/api/kb/{created_id}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    print("[PASS] /api/kb create + live verify + delete")

    # 3. Live Reverse Impact Analysis (T3.2) via HTTP API using configured provider/model
    r = client.post(
        "/api/query",
        json={
            "question": "修改 queryForStationId 方法会影响哪些上游入口 API？",
            "difficulty": "复杂",
        },
    )
    assert r.status_code == 200, r.text
    qres = r.json()
    assert qres["status"] in ("success", "partial") and qres["row_count"] > 0, qres
    print(
        f"[PASS] /api/query [反向影响分析]: status={qres['status']}, rows={qres['row_count']}, "
        f"topo={len(qres['topology']['nodes'])}N/{len(qres['topology']['edges'])}E, subs={len(qres['sub_queries'])}"
    )
    print("  Summary:", qres["summary"].replace("\n", " ")[:180])

    # 4. Markdown Report Export (Req 4)
    qid = qres["query_id"]
    r = client.get(f"/api/history/{qid}/markdown")
    assert r.status_code == 200 and "# 代码图谱查询分析报告" in r.text and "```cypher" in r.text
    print(f"[PASS] /api/history/{qid}/markdown exported ({len(r.text)} chars)")

    # 5. Batch Query Endpoint
    r = client.post(
        "/api/query/batch",
        json={
            "questions": [
                "查找所有 Controller 类型的类",
                "food_delivery 队列的消息由哪个服务发布、哪个服务消费？",
            ],
            "difficulty": "自动",
        },
    )
    assert r.status_code == 200, r.text
    bres = r.json()
    assert bres["total"] == 2 and bres["succeeded"] == 2, bres
    print(f"[PASS] /api/query/batch: {bres['succeeded']}/{bres['total']} succeeded")

    # 6. Static Frontend served at /
    r = client.get("/")
    assert r.status_code == 200 and "代码图谱 Text2Cypher 查询智能体" in r.text
    print("[PASS] GET / serves built React frontend UI")

    print("\nALL END-TO-END CHECKS PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

---
name: reverse-impact
version: "1.0.0"
description: 反向依赖与变更影响分析规范
triggers: ["反向影响分析", "影响", "谁调用了", "上游", "修改", "删除"]
---

# 反向影响分析规范

## 1. 服务级反向依赖（谁调用了指定服务）
- 查上游调用服务与方法：
```cypher
MATCH p=(cm:方法)-[:调用]->(d:下游API)-[:目标服务]->(target:微服务 {服务名称: '<微服务名>'})
RETURN DISTINCT cm.moduleId AS 上游服务, cm.全限定名 AS 调用方法, d.caption AS 调用接口, p
```
- 如需追溯到上游服务的**入口 API**：
```cypher
MATCH p=(entry:上游API)-[:归属于]->(em:方法)-[:调用*0..3]->(cm:方法)-[:调用]->(d:下游API)-[:目标服务]->(target:微服务 {服务名称: '<微服务名>'})
RETURN DISTINCT em.moduleId AS 上游服务, entry.caption AS 上游入口API, cm.方法名 AS 调用方法, d.caption AS 下游接口, p LIMIT 50
```

## 2. 方法变更影响分析（修改某方法影响哪些上游 API）
- 内部反向追踪到本服务入口 API：
```cypher
MATCH p=(u:上游API)-[:归属于]->(ctrl:方法)-[:调用*0..4]->(target:方法 {方法名: '<方法名>'})
RETURN DISTINCT target.moduleId AS 目标服务, target.全限定名 AS 目标方法, u.caption AS 受影响上游API, ctrl.全限定名 AS 入口控制器方法, p LIMIT 50
```
- 跨服务反向影响可进一步由 `u:上游API` 反向匹配 `(d:下游API)-[:调用]->(u)` 找到上游调用服务。

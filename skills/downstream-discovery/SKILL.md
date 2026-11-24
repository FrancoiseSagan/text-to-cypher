---
name: downstream-discovery
version: "1.0.0"
description: 下游服务发现与跨服务调用链追踪规范
triggers: ["下游服务发现", "下游", "调用了哪些", "依赖哪些服务"]
---

# 下游服务发现规范

## 1. 方法级下游服务追踪
从指定方法出发，先沿内部方法调用链（限深 1~4 跳），再通过 `下游API` 到达 `目标服务`：
```cypher
MATCH p=(m:方法 {方法名: '<方法名>'})-[:调用*1..4]->(d:下游API)-[:目标服务]->(svc:微服务)
RETURN DISTINCT m.全限定名 AS 起始方法, d.caption AS 下游API, svc.服务名称 AS 目标微服务, p
```

## 2. 服务级下游发现
从某个微服务下的所有方法出发：
```cypher
MATCH p=(m:方法)-[:调用]->(d:下游API)-[:目标服务]->(target:微服务)
WHERE m.moduleId = '<微服务名>'
RETURN DISTINCT m.moduleId AS 调用方服务, m.方法名 AS 调用方法, d.caption AS 下游API, target.服务名称 AS 目标微服务, p
```

## 3. 端到端跨服务（延伸至目标服务上游API与方法）
如需追踪到被调方的接口和控制器方法，追加可选匹配：
```cypher
OPTIONAL MATCH p2=(d)-[:调用]->(u:上游API)-[:归属于]->(tm:方法)
```
务必使用 `DISTINCT` 去重，并限制最大跳数避免环路扩散。

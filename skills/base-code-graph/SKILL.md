---
name: base-code-graph
version: "1.0.0"
description: 代码图谱基础 Schema 约束、命名规范与拓扑返回规则
triggers: ["default", "单节点查询", "属性过滤", "入口 API 发现"]
---

# 代码图谱基础查询规范

## 1. 节点与属性核心映射
- 微服务节点 `(:微服务)`：使用 `服务名称`（如 `'ts-food-service'`）或 `caption`。
- 类节点 `(:类)`：使用 `简名`、`全限定名`、`类类型`（枚举：`CONTROLLER`, `SERVICE_INTERFACE`, `SERVICE_IMPL`, `OTHER`）、`moduleId`（所属微服务名）。
- 方法节点 `(:方法)`：使用 `方法名`、`全限定名`、`所属类名`、`moduleId`、`是否入口方法`（Boolean）。
- 入口/暴露 API `(:上游API)`：使用 `HTTP方法`、`API路径`、`caption`、`serviceContexts`（数组，用 `'ts-xxx' IN u.serviceContexts` 过滤）。
- 出向 HTTP 调用 `(:下游API)`：使用 `HTTP方法`、`API路径`、`caption`、`目标服务名`、`serviceContexts`。
- 配置节点 `(:配置)`：使用 `key`、`maskedValue`、`configurationKind`。

## 2. 关键图谱拓扑陷阱（必须遵守）
- **类/方法与微服务的归属**：`(:类)` 和 `(:方法)` 与 `(:微服务)` 之间**没有** `[:归属于]` 边！请通过 `m.moduleId = '服务名'` 或 `'服务名' IN m.serviceContexts` 进行过滤。
- **API 与方法的归属**：`(:上游API)-[:归属于]->(:方法)` 和 `(:下游API)-[:归属于]->(:方法)`，方法调用下游 API 为 `(:方法)-[:调用]->(:下游API)`。
- **禁用空标签**：不要使用节点数为 0 的标签（如 `API端点`、`配置文件`、`测试用例`、`调用点`）。
- **只读与限深**：严禁任何写操作；多跳查询必须显式限制步长（如 `[:调用*1..4]`）并加 `DISTINCT` 或 `LIMIT` 防爆炸。
- **拓扑可视化友好**：只要合理，在 `RETURN` 中同时返回关键节点、关系或路径变量（如 `p` 或 `m, r, c`）以及可读的标量别名列，便于前端渲染拓扑图与表格。

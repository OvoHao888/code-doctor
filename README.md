# Code Doctor v1 —— 原始实现

> 这是系统的**初版实现**，保留在此分支用于与当前版本对比。
> **当前版本请切换到 `main` 分支。**

## 形态

5 个 `create_react_agent` 串成一条**直线图**，没有任何条件边：

```
codeparser → bugchecker → fix → report → supervisor → END
```

- 每个节点都跑完整的 ReAct 多轮循环
- 验证只做 `ast.parse`（语法合法 ≠ 能跑起来）
- 没有重试机制，也没有评测

## 这一版存在的问题

完整分析见 `main` 分支 README 的「版本说明」一节，要点：

1. 检测与修复本质是「给定事实 → 产出结构化结论」，一次调用足够，全做成 ReAct 只是增加延迟与 token
2. 图是直线，名为 `Supervisor` 的节点从未参与路由决策
3. 用 `ast.parse` 当修复判据无法证伪
4. MCP 工具因模块导入时解包空列表而**静默失效**
5. 无重试、无评测，无法收敛也无法量化

## 发布前的清理

本分支在上传时做了两处必要处理：

- **移除硬编码密钥**：`mcptools/tools.py` 中原本明文写着 Tavily 的 API Key，
  已改为从环境变量 `TAVILY_API_KEY` 读取。
- **补上 `.gitignore`**：旧版没有该文件，导致 `.env`（含数据库口令与 API Key）
  被提交进版本库。本分支已将其排除。

## 运行

与 `main` 分支一致，但需要自行准备 `.env`（参考 `main` 分支的 `.env.example`）。

# PytestOps Roadmap / Backlog

本文档列出 `PytestOps`（`ntf`）下一阶段**可继续更新**的功能点清单，按优先级和方向分组，便于你按需挑选迭代。

> 说明
>
>- 本清单偏“可实现的工程项”，而非泛泛的想法。
>- 每个条目尽量写清：目标 / 价值 / 交付物 / 风险点。

---

## P0（强烈建议尽快补齐）

### 1. `ntf run` 也支持 `--debugtalk`

- **目标**
  - 让 pytest 直跑（`ntf run`）时，也能加载外部 DebugTalk 文件，复用你旧工程的函数集。
- **价值**
  - 统一 `run-yaml` 和 `run` 的能力，减少“YAML 能跑但 pytest 用例调用不到函数”的割裂。
- **交付物**
  - `ntf run --debugtalk <path>`
  - `ntf.pytest_plugin` 中将 DebugTalk 挂载为 session-scope fixture（可选）
- **风险/注意**
  - DebugTalk 的导入副作用（全局变量、读配置、改 sys.path）。

### 2. `ntf run-yaml` 生成 Allure results（不依赖 pytest）

- **目标**
  - `run-yaml` 直接落 Allure results（case 粒度、step 粒度、request/response attachments）。
- **价值**
  - YAML 驱动迁移期最常用，直接有可视化报告；不必“先转 pytest 再看 Allure”。
- **交付物**
  - `ntf run-yaml ... --allure-dir report/allure-results`
  - 请求/响应自动写附件（headers/body/json，脱敏可选）
- **风险/注意**
  - 需要设计 Allure 的 case/step 结构，避免报告噪音。

### 3. 断言增强：丰富断言类型 + 更清晰的失败 diff

- **目标**
  - 扩充断言：`lt/lte/gt/gte/in/not_in/regex/jsonschema` 等。
  - 断言失败输出更结构化（期望 vs 实际，jsonpath 定位）。
- **价值**
  - 减少老用例迁移成本；提升失败可读性。
- **交付物**
  - `ntf/assertions.py` 扩展
  - 可选：`--assert-verbose` / `--assert-jsonpath-strict`

### 4. 更强的提取能力：变量类型/默认值/多值策略

- **目标**
  - `extract` 支持：
    - 默认值（extract 失败时用默认值）
    - 类型转换（str/int/float/bool）
    - 多值策略（first/last/random/join）
- **价值**
  - 减少 DebugTalk/自定义脚本；提升用例表达力。

---

## P1（建议迭代）

### 5. `run-yaml` 执行模型增强：前置/后置步骤、全局 hooks

- **目标**
  - 支持 suite/case 级别 hooks：`setup_hooks` / `teardown_hooks`。
  - 支持 case 之间的数据依赖声明（显式依赖）。
- **价值**
  - 让业务流场景更自然，减少“靠文件名排序”。

### 6. 运行稳定性：重试、节流、并发、超时策略

- **目标**
  - 重试：按 HTTP code/异常类型/断言失败可选重试。
  - 节流：QPS、并发数。
  - 并发：按文件/按 case 并发执行。
- **价值**
  - 提升跑 CI 的稳定性与速度。
- **交付物**
  - `--retry N --retry-on 5xx,timeout`
  - `--workers N`（并发）
  - `--qps`（节流）

### 7. 环境配置增强：多环境/变量分层/密钥管理

- **目标**
  - `configs/` 支持多 profile（dev/test/stage/prod）。
  - 支持 `.env` / OS env / config yaml 叠加覆盖。
  - 密钥不落盘（env 或 vault）。

### 8. HTTP 能力增强：签名、代理、证书、会话复用策略

- **目标**
  - 统一签名入口（如 sha1/hmac 等）。
  - 支持代理/证书校验开关。
  - session cookie/token 自动维护。

---

## P2（产品化体验/工程质量）

### 9. 更强的 CLI 体验

- **目标**
  - `ntf doctor`：检查依赖（allure/mock deps/端口占用/配置合法性）。
  - `ntf --version` 输出框架版本、python 版本。
  - 子命令提供 shell completion（可选）。

### 10. 日志体系

- **目标**
  - 统一日志：console 精简 + 文件完整。
  - 支持 `--log-level` / `--log-file`。

### 11. 报告体系扩展

- **目标**
  - 除 Allure 外提供 JSON/HTML summary。
  - 失败用例自动聚合（按错误类型、接口、模块）。

### 12. 迁移工具增强

- **目标**
  - `migrate check` 输出更细粒度规则、自动修复建议。
  - `migrate convert` 增加“规范化”能力：
    - 文件命名统一
    - baseInfo 抽取为公共模板
    - 自动补 `--mock-login` 需求提示

---

## P3（可选：向平台化/插件化演进）

### 13. 插件系统

- **目标**
  - 支持通过 entry-points 扩展：
    - 自定义断言
    - 自定义渲染函数
    - 自定义 transport（如 httpx）
    - 自定义报告输出

### 14. 测试数据管理

- **目标**
  - fixtures 数据库/文件夹约定
  - 支持数据工厂（随机生成、唯一性保障）

### 15. 与 CI 集成模板

- **目标**
  - 提供 GitHub Actions / GitLab CI / Jenkins 示例
  - 产物：allure-results、报告、失败截图/日志

---

## 已知问题/体验优化（可选小修）

### A. PowerShell 参数占位符

- PowerShell 中 `<pid>` 会被解析成重定向符号。
- 建议文档示例用：
  - `ntf allure stop --pid 6600`
  - 或使用 `$pid` 变量示例（PowerShell 风格）。

### B. `ntf allure serve` 输出 URL

- 目前 `allure serve` 的 URL 是 Allure 自己打印的；我们 CLI 只打印 pid。
- 可选增强：捕获 stdout 并解析 URL 再输出（或提供 `--print-url`）。

---

## 推荐迭代顺序（建议）

1. `run-yaml` 直接生成 Allure results
2. `ntf run` 支持 `--debugtalk`
3. 断言体系增强（更多断言 + 更好的 diff）
4. hooks + 重试 + 并发
5. migrate convert 的“规范化/自动修复”

# PytestOps Roadmap / Backlog

本文档列出 `PytestOps`（`ntf`）下一阶段**可继续更新**的功能点清单，并结合当前仓库实现情况做了“现状对照”和里程碑拆分。

> 说明
>
>- 本清单偏“可实现的工程项”，而非泛泛的想法。
>- 每个条目尽量写清：目标 / 价值 / 交付物 / 风险点。

---

## 现状对照（基于当前仓库）

- **CLI 命令已存在**
  - `ntf run`：转发到 pytest，支持 `--allure-dir`/`--allure-clean`（见 `ntf/cli.py`）。
  - `ntf run-yaml`：YAML 执行器，支持 `--debugtalk`、`--report`（JSON）、过滤（include/exclude file/case）、`--mock-login`（见 `ntf/cli.py`）。
  - `ntf migrate check|convert`：目前为“轻量复制+检查”（见 `ntf/cli.py`）。
  - `ntf allure serve|stop|generate`：依赖本机 Allure CLI（见 `ntf/cli.py`）。
- **YAML 执行核心已具备**
  - 渲染 `${func()}`：`ntf/renderer.py`（内置少量函数，且支持加载 DebugTalk 文件）。
  - 提取：`ntf/executor.py`（`extract` / `extract_list`），存储：`ntf/extract.py`。
  - 断言：`ntf/assertions.py`（目前集中在 contains/eq/ne/rv/inc 的兼容实现）。
- **当前缺口（Roadmap 将优先补齐）**
  - `run-yaml` 目前**不产出 Allure results**（只能 `--report` 输出 JSON）。
  - 断言类型与失败 diff 还比较弱。
  - 执行模型（hooks、重试、并发、超时策略）尚未产品化。

---

## 优先级定义（约定）

- **P0**
  - 影响“能不能用”的主路径能力；迁移期必须；或明显阻塞后续迭代。
- **P1**
  - 影响“好不好用”的稳定性/扩展性；可与业务迁移并行推进。
- **P2**
  - 体验与工程质量（可观测性、可维护性、发布流程）。
- **P3**
  - 平台化/插件化/生态扩展（可选）。

## 里程碑总览（建议）

| Milestone | 主题 | 优先级 | 关键交付物 | 验收点（最小） |
| --- | --- | --- | --- | --- |
| M0 | `run-yaml` 生成 Allure results（非 pytest） | P0 | `--allure-dir` + attachments | 目录产出 results，Allure 可展示失败原因 |
| M1 | `ntf run` 加载 DebugTalk | P0 | `run --debugtalk` | pytest 跑时 `${func()}` 可解析 |
| M2 | 断言增强 + 失败 diff | P0 | `assertions` 扩展 | 失败信息包含定位/expected/actual |
| M3 | 提取增强 | P0 | extract schema 扩展 | 向后兼容，示例用例覆盖 |
| M4 | hooks/依赖模型 | P1 | setup/teardown + depends_on | 循环依赖报错可读 |
| M5 | 重试/并发/超时 | P1 | `--retry/--workers/--timeout-s` | 用例可控、可复现 |
| M6 | 多环境配置分层 | P1 | profiles + 覆盖策略 | 一条命令切换环境 |
| M7 | HTTP 能力增强 | P1 | proxy/certs/session/sign | 兼容旧语义 |
| M8 | 工程化：质量门禁+发布 | P2 | lint/type/test/release | CI 绿色、可发布 |
| M9 | CLI/日志/doctor | P2 | `ntf doctor` + 日志参数 | 一键定位依赖问题 |

## P0（本周/下周建议落地：里程碑驱动）

### M0. 报告闭环：`run-yaml` 直接生成 Allure results（不依赖 pytest）

- **目标**
  - `run-yaml` 执行时可选生成 Allure results（case 粒度、step 粒度、request/response attachments）。
- **价值**
  - YAML 驱动迁移期最常用，直接可视化；不必“先转 pytest 再看 Allure”。
- **交付物**
  - `ntf run-yaml ... --allure-dir report/allure-results`
  - attachments：request/response（headers/body/json），可选脱敏
- **验收标准**
  - 运行 `ntf run-yaml --cases tests/data --allure-dir report/allure-results` 后，`report/allure-results/` 生成结果文件。
  - 执行失败时 Allure 中能看到失败原因（断言/异常栈）。
- **关联代码**
  - CLI：`ntf/cli.py`（run-yaml 子命令参数与执行循环）
  - 执行：`ntf/executor.py`

- **建议拆分任务（实现顺序）**
  - 1) 定义 Allure writer 抽象（case/step 生命周期）
  - 2) request/response attachment 结构（headers/body/json）
  - 3) 失败映射：断言失败/请求异常/渲染异常
  - 4) 与 `--continue-on-fail` 的汇总一致（最终 exit code 策略）

### M1. `ntf run` 支持 `--debugtalk`（补齐与 run-yaml 的能力对齐）

- **现状**
  - `run-yaml` 已支持 `--debugtalk`（见 `ntf/cli.py`）。
  - `run` 目前仅转发 pytest 参数，未提供 DebugTalk 注入机制。
- **目标**
  - 让 pytest 直跑（`ntf run`）时也能加载外部 DebugTalk 文件，复用旧工程函数集。
- **交付物**
  - `ntf run --debugtalk <path>`
  - 在 pytest session 期间可访问 DebugTalk 提供的函数（渲染/fixture 二选一）
- **验收标准**
  - pytest 用例中调用渲染逻辑时（`${func()}`）可以解析 DebugTalk 函数。
  - DebugTalk 加载失败时提示“缺哪个模块、加了哪些 sys.path”。
- **风险/注意**
  - DebugTalk 导入副作用（全局变量、读配置、改 sys.path）。
  - Windows/CI 环境路径差异。

- **建议拆分任务**
  - 1) 统一 DebugTalk 加载入口（`run` / `run-yaml` 复用同一逻辑）
  - 2) 明确作用域：仅渲染 `${func()}` 生效，避免污染 pytest namespace
  - 3) 错误提示：记录尝试导入路径与失败原因（ModuleNotFoundError 等）

### M2. 断言增强：丰富断言类型 + 更清晰的失败 diff

- **目标**
  - 扩充断言：`lt/lte/gt/gte/in/not_in/regex/jsonschema` 等。
  - 失败输出更结构化（期望 vs 实际、jsonpath 定位、必要时 diff）。
- **交付物**
  - `ntf/assertions.py` 扩展，保持旧语义兼容。
- **验收标准**
  - 新增断言在 `tests/` 中有覆盖（至少每种断言 1 条用例）。
  - 断言失败信息中必须包含：断言类型、定位 key/jsonpath、expected、actual。

- **建议拆分任务**
  - 1) 断言协议梳理（输入：actual/expected/locator；输出：结构化失败信息）
  - 2) 扩展断言集合（数值/集合/正则/jsonschema）
  - 3) 统一 diff 表达（优先 JSON 结构 diff；非 JSON 则 text diff）

### M3. 提取能力增强：默认值/类型转换/多值策略

- **目标**
  - `extract`/`extract_list` 支持：默认值、类型转换（str/int/float/bool）、多值策略（first/last/random/join）。
- **交付物**
  - 规则设计（YAML schema）+ `ntf/executor.py` 实现。
- **验收标准**
  - 旧 YAML 不改也能跑（向后兼容）。
  - 新 schema 的示例用例在 `tests/` 可跑通。

- **建议拆分任务**
  - 1) schema 设计：保持旧字段不变，新能力通过可选字段扩展
  - 2) 转换与策略：在 ExtractStore 落盘前完成（避免 store 内部“同时存多类型”）
  - 3) 错误可读：extract 失败时输出 source 表达式与响应片段（可截断）

---

## P1（中期：能力完善与稳定性）

### M4. `run-yaml` 执行模型增强：hooks / 显式依赖

- **目标**
  - suite/case 级 hooks：`setup_hooks` / `teardown_hooks`。
  - case 之间显式依赖声明（避免靠文件名排序）。
- **验收标准**
  - hooks 失败时可选择“终止”或“继续”（与 `--continue-on-fail` 协作）。
  - 依赖缺失/循环依赖能给出可读错误。

### M5. 运行稳定性：重试 / 并发 / 超时策略

- **目标**
  - 重试：按 HTTP code/异常类型/断言失败可选重试。
  - 并发：按文件/按 case 并发。
  - 超时：全局默认 + 单 case 覆盖。
- **交付物（CLI 方向）**
  - `--retry N --retry-on 5xx,timeout`
  - `--workers N`
  - `--timeout-s`

### M6. 环境配置增强：多环境/变量分层

- **目标**
  - `configs/` 支持 profile（dev/test/stage/prod）。
  - env 覆盖策略清晰（OS env > profile yaml > default yaml）。

### M7. HTTP 能力增强：签名/代理/证书/会话

- **目标**
  - 统一签名入口（sha1/hmac 等）。
  - 代理/证书校验开关。
  - session cookie/token 自动维护策略。

---

## P2（产品化体验/工程质量）

### M8. 工程化闭环：质量门禁（lint/type/test）+ 可发布版本

- **目标**
  - 建立最小质量门禁，避免功能增加后回归。
  - 形成可发布的版本策略（本地/CI 均可安装使用）。
- **交付物**
  - 命令：`python -m pip install -e .`、`python -m build` 产物可用
  - 质量门禁：单测、基础 lint、基础类型检查（至少不报错）
  - 版本：`ntf --version` 与包版本一致
- **验收标准**
  - 在干净环境中从源码安装后，`ntf --help` / `ntf run-yaml --help` 可用
  - CI（若已接入）在 pull request 上必跑并出结果

### M9. 可观测性与诊断：日志体系 + `ntf doctor`

- **目标**
  - 统一日志输出，既适合本地排错也适合 CI 留档。
  - 一键诊断依赖与常见错误（Allure CLI、端口占用、配置合法性、mock 状态）。
- **交付物**
  - `--log-level` / `--log-file`
  - `ntf doctor`（输出检查项与建议修复动作）
- **验收标准**
  - `ntf doctor` 在缺依赖时能给出“安装什么/配置什么/下一步执行什么”
  - 当启用 `--log-file` 时，关键请求链路与失败原因可追溯

---

### 10. 更强的 CLI 体验

- **目标**
  - `ntf doctor`：检查依赖（allure/mock deps/端口占用/配置合法性）。
  - `ntf --version` 输出框架版本、python 版本。
  - 子命令提供 shell completion（可选）。

### 11. 日志体系

- **目标**
  - 统一日志：console 精简 + 文件完整。
  - 支持 `--log-level` / `--log-file`。

### 12. 报告体系扩展

- **目标**
  - 除 Allure 外提供 JSON/HTML summary。
  - 失败用例自动聚合（按错误类型、接口、模块）。

### 13. 迁移工具增强

- **目标**
  - `migrate check` 输出更细粒度规则、自动修复建议。
  - `migrate convert` 增加“规范化”能力：
    - 文件命名统一
    - baseInfo 抽取为公共模板
    - 自动补 `--mock-login` 需求提示

---

## P3（可选：向平台化/插件化演进）

### 14. 插件系统

- **目标**
  - 支持通过 entry-points 扩展：
    - 自定义断言
    - 自定义渲染函数
    - 自定义 transport（如 httpx）
    - 自定义报告输出

### 15. 测试数据管理

- **目标**
  - fixtures 数据库/文件夹约定
  - 支持数据工厂（随机生成、唯一性保障）

### 16. 与 CI 集成模板

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

1. `run-yaml` 直接生成 Allure results（M0）
2. `ntf run` 支持 `--debugtalk`（M1）
3. 断言体系增强（M2） + 提取增强（M3）
4. hooks + 重试 + 并发（M4/M5）
5. migrate convert 的“规范化/自动修复”（可并行推进）

---

## Progress Update (2026-03-06)

P1 milestones implemented in current codebase:

- M4: `run-yaml` supports `setup_hooks` / `teardown_hooks` / `depends_on`, with dependency cycle detection and skip-on-dependency-failure behavior.
- M5: added `--retry`, `--retry-on`, `--workers`, `--timeout-s`.
- M6: added profile loading (`--profile`) and layered config override strategy (`env > profile > default`).
- M7: HTTP transport supports proxy/cert/verify/session options and optional request signing.

## Progress Update (2026-03-06, P2)

P2 milestones implemented:

- M8: added quality gate setup in project config (dev extras for ruff/mypy/build) and CI workflow (`.github/workflows/ci.yml`) running lint/type/test/build.
- M9: added CLI logging options (`--log-level`, `--log-file`) and `ntf doctor` diagnostics command; also added `ntf --version` output.

## Progress Update (2026-03-06, P3)

P3 milestones implemented:

- M14 plugin system: entry-points based loading plus runtime registration in `ntf.plugins`, integrated with assertions/renderer/run-yaml transport/reporter extension points.
- M15 test data management: `FixtureStore` convention (`tests/fixtures`) and `data_factory` random/unique helpers.
- M16 multi-CI templates: added `.gitlab-ci.yml` and `Jenkinsfile` (GitHub Actions already present).

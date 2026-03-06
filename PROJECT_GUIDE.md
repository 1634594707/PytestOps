# PytestOps 项目功能与使用指南

## 1. 这是什么项目

`PytestOps` 是一个面向 API 自动化测试的工程化框架，支持：

- YAML 数据驱动用例执行
- 断言与参数提取
- Mock 服务联调
- Allure 报告
- 插件扩展（断言、函数、传输层、报告器、渲染器）
- 钉钉通知
- 诊断命令与日志体系

目标是把“写请求 + 校验结果”的流程标准化，降低接口测试成本，并支持团队规模化维护。

---

## 2. 有什么用

适用于以下场景：

- 接口回归测试：快速批量执行 API 用例
- 测试左移：开发阶段本地自测、联调
- CI 持续集成：PR 自动跑质量门禁与用例
- 旧框架迁移：把历史 YAML 用例迁移到统一执行器
- 自动化结果通知：通过钉钉推送执行摘要

核心收益：

- 用例与代码解耦（YAML 驱动）
- 统一断言/提取/渲染机制
- 命令行可编排，适合本地与 CI
- 插件机制可按团队需求扩展

---

## 3. 功能总览

### 3.1 YAML 数据驱动

- 支持 `ntf run-yaml` 直接执行 YAML 文件/目录/通配符
- 支持 include/exclude 过滤文件与 case

### 3.2 参数提取

- 支持 JSONPath 和正则提取
- 支持提取增强 schema（`default` / `type` / `strategy`）

### 3.3 断言体系

- 已支持：`contains/eq/ne/rv/inc`
- 已扩展：`lt/lte/gt/gte/in/not_in/regex/jsonschema`

### 3.4 执行控制

- 支持 `setup_hooks` / `teardown_hooks`
- 支持 `depends_on` 依赖与循环检测
- 支持 `--retry` / `--retry-on` / `--workers` / `--timeout-s`

### 3.5 环境配置与 HTTP 能力

- 支持 `--profile` 多环境切换
- 覆盖优先级：`env > profile > default`
- 支持 proxy / verify / cert / session
- 支持请求签名（hmac/sha1）

### 3.6 CLI 工具链

- `run` / `run-yaml` / `mock` / `allure` / `migrate` / `doctor`
- 全局支持：`--log-level`、`--log-file`、`--version`
- 自动加载当前目录 `.env`（不覆盖已有环境变量）

### 3.7 插件化

- 插件入口：
  - `ntf.assertions`
  - `ntf.functions`
  - `ntf.transports`
  - `ntf.reporters`
  - `ntf.renderers`

### 3.8 钉钉通知

- pytest 汇总通知（插件内）
- run-yaml 汇总通知（命令行与环境变量都支持）

---

## 4. 怎么操作（快速上手）

### 4.1 安装

```bash
python -m pip install -e .
```

开发依赖（lint/type/build）：

```bash
python -m pip install -e .[dev]
```

### 4.2 环境变量配置（推荐）

在项目根目录新建 `.env`（可由 `.env.example` 复制）：

```env
NTF_BASE_URL=http://127.0.0.1:8787
NTF_TIMEOUT_S=60

NTF_DINGDING_ENABLED=true
NTF_DINGDING_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=REPLACE_ME
NTF_DINGDING_SECRET=SEC_REPLACE_ME
```

> `ntf` 会自动读取当前目录 `.env`。

### 4.3 启动 Mock（本地联调）

```bash
ntf mock start
ntf mock status
```

### 4.4 执行 YAML 用例

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data
```

失败后继续执行：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --continue-on-fail
```

常用增强参数：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data \
  --retry 1 --retry-on request,timeout,5xx \
  --workers 2 --timeout-s 15 \
  --profile test
```

### 4.5 Allure 报告

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --allure-dir report/allure-results
ntf allure generate --results report/allure-results --out report/allure-report --clean
ntf allure serve --dir report/allure-results
```

### 4.6 钉钉通知（run-yaml）

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data \
  --dingding-enabled \
  --dingding-webhook "<webhook>" \
  --dingding-secret "<secret>"
```

或用 `.env` 提供 `NTF_DINGDING_*` 配置，执行时无需再传。

### 4.7 诊断与版本

```bash
ntf --version
ntf doctor --config configs/default.yaml --profile test
```

---

## 5. 质量门禁与 CI

本地建议执行：

```bash
ruff check ntf tests
mypy ntf
pytest -q
python -m build
```

仓库已提供 CI 模板：

- GitHub Actions：`.github/workflows/ci.yml`
- GitLab CI：`.gitlab-ci.yml`
- Jenkins：`Jenkinsfile`

---

## 6. 常见问题

### Q1: 连接 `127.0.0.1:8787` 被拒绝

说明 mock 服务没启动或端口不可达。

```bash
ntf mock start
ntf mock status
```

### Q2: 修改了 `.env` 但不生效

请确认：

- `.env` 在当前执行目录下
- key 格式正确（`KEY=VALUE`）
- 当前系统环境里是否已有同名变量（默认不覆盖）

### Q3: 为什么有 case 失败

部分示例文件（如 `sample_api_pass_fail.yaml`）包含故意失败用例，用于验证失败链路与报告效果。

---

## 7. 建议的日常使用流程

1. 配置 `.env`（基础 URL、钉钉）
2. `ntf mock start`（本地联调时）
3. `ntf run-yaml ... --continue-on-fail`
4. 失败时看日志 + `report` + Allure
5. 提交前执行 `ruff/mypy/pytest`


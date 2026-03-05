# PytestOps

一个**分层清晰、可扩展、可插件化**的 pytest 自动化测试框架骨架（API-first）。

## 目标

- 保留你现有框架的核心能力：YAML 数据驱动、参数提取（extract）、断言（contains/eq/ne/rv）、pytest fixture。
- 重构为更清晰的分层：`config` / `transport` / `executor` / `assertion` / `extract_store`。
- 降低耦合：测试用例不依赖 Allure，也不把 pytest.fail 写进底层请求层。

## 目录结构

- `ntf/`
  - 框架核心代码
- `configs/`
  - 环境与运行配置（yaml）
- `tests/`
  - 示例用例（包含 YAML 驱动示例 + 纯 Python 示例）

## 快速开始

### 1. 安装依赖

在 `PytestOps` 目录下执行：

```bash
python -m pip install -e .
```

### 2. 运行示例

```bash
pytest
```

## mock_server（本地联调）

本项目可以内置一个可运行的 mock 服务（默认监听 `127.0.0.1:8787`），用于联调 `ntf run-yaml`。

### 启动 mock_server

在 `PytestOps/mock_server/api_server/base` 目录执行：

```bash
python flask_service.py
```

如果提示缺依赖（例如 `flask_jwt_extended`），按报错安装即可。

### 3. CLI（可选）

```bash
ntf run --config configs/default.yaml
```

带 Allure（可选）：

```bash
ntf run --config configs/default.yaml --allure-dir report/allure-results --allure-clean
```

### 4. CLI：直接跑 YAML 用例（推荐迁移期使用）

跑单个 YAML：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data/sample_api.yaml
```

说明：示例 YAML 默认请求本地 mock_server（`127.0.0.1:8787`），运行前请先执行：

```bash
ntf mock start
```

跑一个目录下所有 YAML：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data
```

跑通配符：

```bash
ntf run-yaml --config configs/default.yaml --cases "tests/data/*.yaml"
```

遇到失败继续跑（汇总所有失败）：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --continue-on-fail
```

预置变量（给 `${get_extract_data(...)}` 用）：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --vars token=t-123 user_id=123456
```

过滤（正则）：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --include-file "legacy" --exclude-case "skip"
```

失败报告落盘：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --continue-on-fail --report report/run-yaml.json
```

mock_server 预登录（自动注入 token，适合旧用例里依赖 `${get_extract_data(token)}` 的场景）：

```bash
ntf run-yaml --config configs/default.yaml --cases ..\\Test-Automation-Framework-main\\testcase --mock-login --continue-on-fail --report report/legacy-run.json
```

指定 mock_server 登录账号（可选）：

```bash
ntf run-yaml --config configs/default.yaml --cases ..\\Test-Automation-Framework-main\\testcase --mock-login --mock-user test01 --mock-pass admin123
```

注意：文档里若出现 `...` 仅表示省略，请不要把 `...` 当作命令的一部分复制执行。

加载 DebugTalk（可选，自定义 `${func()}` 函数）：

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --debugtalk ..\\Test-Automation-Framework-main\\debugtalk.py
```

## 一键 mock_server

```bash
ntf mock status
ntf mock start
ntf mock stop
```

## 迁移检查（不执行用例，只做结构扫描）

```bash
ntf migrate check --path ..\\Test-Automation-Framework-main\\testcase --out report/migrate-check.json
```

## 迁移转换（非破坏性复制旧用例到新目录）

```bash
ntf migrate convert --src ..\\Test-Automation-Framework-main\\testcase --dst tests/legacy --index report/migrate-index.json
```

## Allure wrapper（可选）

生成 Allure 结果：

```bash
ntf run --config configs/default.yaml --allure-dir report/allure-results --allure-clean
```

一键打开 Allure：

```bash
ntf allure serve --dir report/allure-results
```

停止 Allure（可选）：

`ntf allure serve` 会输出 pid，可用下面命令结束进程：

```bash
ntf allure stop --pid <pid>
```

生成静态报告：

```bash
ntf allure generate --results report/allure-results --out report/allure-report --clean
```

## YAML 用例格式（示例）

见：`tests/data/sample_api.yaml`

## 兼容旧框架能力

### 1. `${func()}` 渲染（DebugTalk 风格）

框架会在请求执行前，对 `header/params/data/json` 等字段进行渲染，支持：

```text
${get_extract_data(token)}
${get_extract_data(list_key,0)}
```

当前默认实现位于：`ntf/renderer.py`（内置 `get_extract_data`，基于 `ExtractStore`）。

### 2. `extract_list`

YAML 中支持 `extract_list`：

- JSONPath（以 `$` 开头）将返回列表
- 正则表达式将使用 `re.findall` 返回列表

## pytest 插件（运行摘要/钉钉通知）

本项目默认启用 `ntf.pytest_plugin`，每次运行结束会输出结果摘要。

### 启用钉钉通知（可选）

设置环境变量：

- `NTF_DINGDING_ENABLED=true`
- `NTF_DINGDING_WEBHOOK=<你的 webhook>`
- `NTF_DINGDING_SECRET=<加签密钥>`

然后执行 `pytest` 即可。

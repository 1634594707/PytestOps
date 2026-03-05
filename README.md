# PytestOps

一个**分层清晰、可扩展、可插件化**的 pytest 自动化测试框架（API-first）。

## 项目简介

PytestOps 是一个基于 pytest 的现代化 API 自动化测试框架，旨在为测试团队提供一套**高内聚、低耦合**的测试解决方案。

### 核心特性

- **YAML 数据驱动**：支持纯 YAML 编写测试用例，实现业务与代码分离
- **灵活的参数提取**：支持 JSONPath 和正则表达式提取响应数据
- **强大的断言能力**：支持多种断言类型（contains/eq/ne/rv/inc 等）
- **完善的 CLI 工具**：提供丰富的命令行工具，支持用例执行、报告生成、Mock 服务等
- **插件化设计**：支持自定义 DebugTalk 函数、断言、渲染器等扩展
- **钉钉通知**：内置钉钉机器人通知功能，测试结果实时推送

## 目标

- 保留现有框架的核心能力：YAML 数据驱动、参数提取（extract）、断言（contains/eq/ne/rv）、pytest fixture
- 重构为更清晰的分层：`config` / `transport` / `executor` / `assertion` / `extract_store`
- 降低耦合：测试用例不依赖 Allure，也不把 pytest.fail 写进底层请求层

## 目录结构

```
PytestOps/
├── ntf/                      # 框架核心代码
│   ├── cli.py               # CLI 命令行工具
│   ├── executor.py          # 用例执行器
│   ├── assertions.py        # 断言实现
│   ├── extract.py           # 参数提取
│   ├── renderer.py          # 变量渲染器
│   ├── http.py              # HTTP 请求封装
│   ├── config.py            # 配置管理
│   ├── pytest_plugin.py     # pytest 插件
│   ├── allure_results.py    # Allure 结果处理
│   └── integrations/        # 第三方集成
│       └── dingding.py      # 钉钉通知
├── configs/                 # 环境与运行配置（YAML）
├── tests/                   # 示例用例
│   ├── data/               # YAML 用例示例
│   └── legacy/             # 旧用例示例
├── mock_server/            # 内置 Mock 服务
├── report/                 # 测试报告目录
└── pyproject.toml          # 项目配置
```

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

### 3. 使用 CLI 运行

```bash
ntf run --config configs/default.yaml
```

带 Allure 报告（可选）：

```bash
ntf run --config configs/default.yaml --allure-dir report/allure-results --allure-clean
```

## Mock 服务（本地联调）

本项目内置了一个可运行的 Mock 服务（默认监听 `127.0.0.1:8787`），用于本地联调。

### 启动 Mock 服务

在 `PytestOps/mock_server/api_server/base` 目录执行：

```bash
python flask_service.py
```

如果提示缺依赖（例如 `flask_jwt_extended`），按报错安装即可。

### 使用 CLI 管理 Mock 服务

```bash
ntf mock status   # 查看状态
ntf mock start    # 启动服务
ntf mock stop     # 停止服务
```

## YAML 用例运行

### 运行单个 YAML 文件

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data/sample_api.yaml
```

> **注意**：示例 YAML 默认请求本地 mock_server（`127.0.0.1:8787`），运行前请先启动 Mock 服务：
> ```bash
> ntf mock start
> ```

### 运行目录下所有 YAML

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data
```

### 使用通配符

```bash
ntf run-yaml --config configs/default.yaml --cases "tests/data/*.yaml"
```

### 遇到失败继续运行（汇总所有失败）

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --continue-on-fail
```

### 预设变量

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --vars token=t-123 user_id=123456
```

### 过滤用例（正则）

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --include-file "legacy" --exclude-case "skip"
```

### 生成失败报告

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --continue-on-fail --report report/run-yaml.json
```

### Mock 登录（自动注入 Token）

```bash
ntf run-yaml --config configs/default.yaml --cases <用例目录> --mock-login --continue-on-fail
```

指定 Mock 登录账号（可选）：

```bash
ntf run-yaml --config configs/default.yaml --cases <用例目录> --mock-login --mock-user test01 --mock-pass admin123
```

### 加载 DebugTalk（自定义函数）

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --debugtalk <path_to_debugtalk.py>
```

## 迁移工具

### 迁移检查（结构扫描）

```bash
ntf migrate check --path <旧用例目录> --out report/migrate-check.json
```

### 迁移转换（非破坏性复制）

```bash
ntf migrate convert --src <旧用例目录> --dst tests/legacy --index report/migrate-index.json
```

## Allure 报告

### 生成 Allure 结果

```bash
ntf run --config configs/default.yaml --allure-dir report/allure-results --allure-clean
```

### 一键打开 Allure 报告

```bash
ntf allure serve --dir report/allure-results
```

### 停止 Allure 服务

`ntf allure serve` 会输出 PID，可用下面命令结束进程：

```bash
ntf allure stop --pid <pid>
```

### 生成静态报告

```bash
ntf allure generate --results report/allure-results --out report/allure-report --clean
```

## YAML 用例格式

详见示例文件：`tests/data/sample_api.yaml`

### 基础结构

```yaml
- name: 用例名称
  request:
    method: GET
    url: http://example.com/api
    headers:
      Content-Type: application/json
    params:
      key: value
  validate:
    - eq: ["status_code", 200]
    - contains: ["body.message", "success"]
```

### 参数提取

```yaml
- name: 提取用户ID
  request:
    method: POST
    url: http://example.com/api/login
    json:
      username: test
      password: 123456
  extract:
    - user_id: "$.data.userId"        # JSONPath 提取
    - token: "token_(\\w+)"            # 正则提取
```

### 提取列表

```yaml
extract_list:
  - ids: "$..items[*].id"              # JSONPath 返回列表
  - names: "name(\\w+)"                # 正则返回列表
```

## 兼容旧框架能力

### 1. `${func()}` 渲染（DebugTalk 风格）

框架会在请求执行前，对 `header/params/data/json` 等字段进行渲染，支持：

```text
${get_extract_data(token)}
${get_extract_data(list_key, 0)}
```

当前默认实现位于 `ntf/renderer.py`（内置 `get_extract_data`，基于 `ExtractStore`）。

### 2. `extract_list`

YAML 中支持 `extract_list`：
- JSONPath（以 `$` 开头）将返回列表
- 正则表达式将使用 `re.findall` 返回列表

## pytest 插件

本项目默认启用 `ntf.pytest_plugin`，每次运行结束会输出结果摘要。

### 启用钉钉通知（可选）

设置环境变量：

```bash
# 启用钉钉通知
set NTF_DINGDING_ENABLED=true
# 钉钉 Webhook 地址
set NTF_DINGDING_WEBHOOK=<你的 webhook>
# 钉钉加签密钥
set NTF_DINGDING_SECRET=<加签密钥>
```

然后执行 `pytest` 即可。

## 技术栈

- **Python**: >=3.12
- **测试框架**: pytest >=8.3.2
- **HTTP 客户端**: requests >=2.32.3
- **报告工具**: Allure
- **配置格式**: YAML

## 许可证

MIT License

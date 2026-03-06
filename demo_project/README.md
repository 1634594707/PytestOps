# Demo Test Project

这是一个最小可运行的演示测试项目，展示 `PytestOps` 的典型能力：

- YAML 数据驱动
- 参数提取（extract / extract_list）
- 断言校验
- case 依赖（depends_on）
- hooks（setup_hooks / teardown_hooks）
- 变量渲染（`${func()}`）

## 目录结构

```text
demo_project/
  configs/
    demo.yaml
  cases/
    user_flow.yaml
```

## 运行步骤

1. 启动 mock 服务

```powershell
ntf mock start
```

2. 执行演示用例

```powershell
ntf run-yaml --config demo_project/configs/demo.yaml --cases demo_project/cases --continue-on-fail
```

3. 生成报告（可选）

```powershell
ntf run-yaml --config demo_project/configs/demo.yaml --cases demo_project/cases --allure-dir report/allure-results
```

## 你可以怎么改

- 修改 `configs/demo.yaml` 的 `base_url` 对接你的项目接口
- 在 `cases/` 下新增你的业务 YAML
- 用 `extract` 提取上游返回值，在后续 case 用 `${get_extract_data(key)}` 引用

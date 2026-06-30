[English](CONTRIBUTING.md) | **简体中文**

# 为 Octopus LinkedIn 贡献

感谢你有意改进 Octopus LinkedIn。欢迎各种形式的贡献——bug 报告、功能想法、
文档、代码。

## 开发环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

要运行需要联网的工具，先用你自己的 LinkedIn 开发者应用授权一次（见 README）。
单元测试**不需要**任何凭据。

## 运行检查

```bash
ruff check .          # 代码规范
ruff format --check . # 格式
pytest                # 测试
```

提交 PR 前请确保这三项都通过。CI 会跑同样的检查。

## 指南

- 保持对外暴露的工具面小而清晰——每个 MCP 工具的 docstring 就是大模型用来决定
  如何调用它的依据，务必精确。
- 任何会把数据发往 LinkedIn 的操作，工具名必须一眼能看出来。纯本地操作（草稿、
  品牌语气）绝不能发起网络请求。
- 行为变更要补充或更新测试。草稿流程、发布关口、内容安全（SSRF/注入防护）都有
  完整单测，请保持这个标准。
- 风格与现有代码一致；`ruff format` 是格式的唯一标准。

## 报告 bug

开 issue 时附上复现步骤、期望与实际行为、以及你的环境（操作系统、Python 版本）。
安全问题见 [SECURITY.zh-CN.md](SECURITY.zh-CN.md)——**请勿**公开开 issue。

## 行为准则

本项目遵循[贡献者公约](CODE_OF_CONDUCT.zh-CN.md)。参与即表示你同意遵守。

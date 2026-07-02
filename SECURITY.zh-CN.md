[English](SECURITY.md) | **简体中文**

# 安全策略

## 报告漏洞

**请勿**为安全漏洞公开开 issue。

请通过 GitHub Security Advisories（仓库 Security 标签页的 "Report a vulnerability"）
或邮件 **security@octopusos.ai**（维护者：Ran Tao，ran@octopusos.ai）私下报告。
请附上描述、复现步骤和影响。我们会争取在几个工作日内确认。

## 凭据处理

Octopus LinkedIn 通过 OAuth 代表你与 LinkedIn 通信。以下文件按机密对待，切勿提交：

- **`.env`** —— 存放 `LINKEDIN_CLIENT_SECRET` 及各家 LLM 的 API key。默认已 gitignore。
- **`token.json`** —— 存放访问（及刷新）令牌。默认已 gitignore，并以 `0600` 权限写入。

如果 Client Secret 不慎泄露，立即在 LinkedIn 开发者后台重新生成
（App → Auth → Generate a new Client Secret）。已有的访问令牌在过期前仍可用；
重跑 `python -m linkedin.auth` 即可重新授权。

## 范围说明

- 令牌只存在本地，仅发送至 `api.linkedin.com` 和 `www.linkedin.com`。
- 草稿流程按设计是纯本地的：撰写与批准草稿不会发起网络请求。只有 `publish_draft`
  和直接发布类工具会把数据发往 LinkedIn。
- 大模型 API key 只放在请求头里（不放 URL），不会被日志记录；上游报错详情会被截断后
  返回，不会原样透传。
- `repurpose_url` 只抓取公网 http(s) 地址（80/443 端口），并把 DNS 解析结果**绑定到
  连接**上，从源头上拦截 SSRF / DNS 重绑定；抓取的网页内容会被当作"不可信数据"包裹后
  再交给大模型，以降低提示词注入风险。

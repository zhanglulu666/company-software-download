# 📦 公司常用软件下载站

Windows 必备软件合集，每周一自动更新安装包。基于 GitHub Pages + Actions 构建。

## 🌐 访问地址

```
https://<你的用户名>.github.io/<仓库名>/
```

## 📋 包含软件

| 软件 | 类别 | 下载方式 |
|------|------|---------|
| 谷歌 Chrome | 浏览器 | 官方直链 |
| 搜狗浏览器 | 浏览器 | 官网抓取 |
| 企业微信 | 通讯办公 | 官网抓取 |
| Zoom 会议 | 通讯办公 | 官方直链 |
| 腾讯会议 | 通讯办公 | 官网抓取 |
| Office Tool Plus | 系统工具 | GitHub Releases |
| 7-Zip | 系统工具 | GitHub Releases |
| WinRAR | 系统工具 | 中文官网抓取 |
| KMS 激活脚本 | 系统工具 | GitHub Releases (加密) |

## 🔄 自动更新

- **定时**: 每周一凌晨 0:00 (北京时间) 自动运行
- **手动**: 在 Actions 页面点击 `Run workflow`
- 只下载版本有变化的软件，避免重复流量
- 安装包上传到 GitHub Releases

## 🛠️ 本地运行

```bash
pip install requests beautifulsoup4 pyminizip
mkdir -p downloads
python scripts/update.py
```

然后打开 `index.html` 即可预览网站。

## 🔒 KMS 说明

KMS 激活脚本使用 [Microsoft Activation Scripts (MAS)](https://github.com/massgravel/Microsoft-Activation-Scripts)，为开源合法脚本。下载包已加密，密码请咨询管理员。

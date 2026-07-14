# 📦 公司常用软件下载站

Windows 必备软件合集，一键直达官网下载。

## 🌐 访问地址

https://zhanglulu666.github.io/company-software-download/

## 📋 软件列表

| 软件 | 下载方式 |
|------|---------|
| 谷歌 Chrome | 跳转官网 |
| 搜狗浏览器 | 跳转官网 |
| 企业微信 | 跳转官网 |
| Zoom 会议 | 跳转官网 |
| 腾讯会议 | 跳转官网 |
| Office Tool Plus | 跳转官网 |
| 7-Zip | 跳转官网 |
| WinRAR | 跳转官网 |
| KMS 激活脚本 | 本地下载（联系管理员） |

## 🛠 如何添加/更新软件

编辑 `software.json`，添加新条目：

```json
{
  "id": "my-software",
  "name": "软件名称",
  "name_en": "Software Name",
  "description": "软件描述",
  "category": "分类",
  "download_url": "https://官网下载地址",
  "download_type": "link",
  "icon": "📦"
}
```

如需托管安装包，把文件放到 `files/` 目录，设置 `download_type: "local"`，`download_url: "files/文件名.exe"`。

## 🚀 部署

推送代码到 `main` 分支即自动部署到 GitHub Pages。
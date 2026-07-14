# 手动上传文件目录

## 使用方法
将需要托管下载的软件安装包放到这个目录，然后在 `software.json` 中配置 `download_type: "local"` 和 `download_url: "files/文件名.exe"`。

## 示例
1. 把 `kms-mas.zip` 放到这个目录
2. `software.json` 中对应的 download_url 设置为 `files/kms-mas.zip`
3. 推送后，网站上的「直接下载」按钮会指向这个文件

## 文件大小限制
GitHub 限制单个文件不超过 100MB。大文件建议用 Git LFS 或放外部网盘。
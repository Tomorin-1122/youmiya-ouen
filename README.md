# 羊宫国 — 羊宮妃那応援站

羊宫妃那粉丝应援站。展示照片墙、百科、心声等内容，支持深色模式和中日双语。

🌐 **在线访问**：https://youmiya.top

## 功能

### 📷 照片墙
- 瀑布流布局，点击放大查看
- 支持左右键导航和点赞功能

### 📖 百科
- 仿萌娘百科风格，包含经历、代表角色、人际关系等
- 数据来源：萌娘百科

### 💬 心声
- 记录羊宫妃那的采访和推文
- 卡片式布局，支持按类型筛选

### 🌙 黑夜模式
- 侧边栏底部按钮切换，自动记忆偏好

### 🇯🇵 日语界面
- 页面标题栏右侧切换，自动记忆偏好

### 📅 那年今日
- 自动检测重要日子并弹窗提醒
- 生日（3月26日）有特殊效果

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | 纯 HTML/CSS/JS，无框架 |
| 抓取 | Python + CDP WebSocket |
| 部署 | Cloudflare Workers（免费） |
| 域名 | youmiya.top |

## 项目结构

```
应援站/
├── gallery.html         # 主页面
├── serve.py             # 本地服务器
├── cdp_scrape.py        # 抓取脚本
├── config.json          # 账号配置
├── deploy/              # 部署目录
│   ├── gallery.html
│   ├── worker.js        # Cloudflare Worker 脚本
│   ├── wrangler.toml    # 部署配置
│   └── data/
└── data/
    ├── posts.json       # 照片元数据
    ├── wiki.json        # 百科数据
    ├── voices.json      # 心声数据
    ├── important-days.json
    ├── images/          # 照片墙图片
    ├── wiki/            # 百科图片
    ├── voices/          # 心声配图
    └── avatar/          # 头像
```

## 本地开发

### 启动服务器

```bash
pip install -r requirements.txt
python serve.py
```

访问 http://localhost:8800

### 抓取新照片

```bash
# 启动 Chrome（带 CDP）
start_chrome.bat

# 抓取
python cdp_scrape.py
```

## 部署更新

### 修改代码后部署

```bash
# 1. 复制文件到 deploy 目录
copy gallery.html deploy\
xcopy /E /Y data\* deploy\data\

# 2. 部署到 Cloudflare
cd deploy
npx wrangler deploy
```

### 添加图片

1. 把新图片放到 `data/images/`
2. 更新 `data/posts.json`
3. 复制到 `deploy` 并部署

## CDP 抓取原理

```
Chrome (CDP port 9223)
    ↓ WebSocket
cdp_scrape.py
    ↓ 注入 JS 提取图片
data/images/*.jpg
```

## 更新日志

### 2026-06-23
- 修复 XSS 注入风险
- 修复服务器安全问题（绑定地址、异常处理）
- 重构 cdp_scrape.py 支持增量抓取
- 优化 serve.py 添加缓存和多线程
- 注册域名 youmiya.top
- 部署到 Cloudflare Workers
- 绑定自定义域名

### 历史更新
- 新增心声、关于页面
- 新增黑夜模式、日语界面
- 新增那年今日弹窗
- 百科页面添加顶图横幅

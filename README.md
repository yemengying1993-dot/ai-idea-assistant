# 🤖 智能想法记录助手

像发微信一样记录想法，AI 自动分类，Markdown 文档沉淀。

## ✨ 功能特点

- 📱 **随时记录** - 飞书直接发消息，3秒完成
- 🤖 **智能分类** - AI/关键词双模式，8大类自动归档
- 📝 **文档沉淀** - Markdown 格式，支持全文搜索
- 📊 **报告生成** - /日报、/周报、/月报一键查看
- 🔄 **灵活切换** - AI 模式 ↔ 关键词模式实时切换

## 🛠️ 技术栈

- **后端**: Flask (Python)
- **AI**: Claude API (Anthropic)
- **平台**: 飞书开放平台
- **内网穿透**: ngrok
- **存储**: Markdown 文件

## 📦 安装

```bash
# 1. 克隆仓库
git clone <your-repo-url>
cd ai-idea-assistant

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的配置
```

## ⚙️ 配置

创建 `.env` 文件：

```bash
# 飞书配置（必填）
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_VERIFY_TOKEN=your_feishu_verify_token  # 飞书事件订阅 → 验证令牌

# Claude API（可选，用于 AI 分类）
ANTHROPIC_API_KEY=sk-ant-xxxxx

# 企业微信配置（可选）
WEWORK_TOKEN=
WEWORK_ENCODING_AES_KEY=
WEWORK_CORP_ID=

# 端口（可选，默认 5001）
PORT=5001
```

> **安全提示**：`FEISHU_VERIFY_TOKEN` 用于验证飞书 Webhook 请求的合法性，强烈建议配置。
> 在飞书开放平台 → 你的应用 → 事件订阅 页面可以找到「验证令牌」。

## 🚀 运行

```bash
# 1. 启动 Bot
python idea_bot.py

# 2. 启动 ngrok（新终端）
ngrok http 5001

# 3. 配置飞书 Webhook URL
# 进入飞书开放平台 → 事件订阅
# 填入：https://your-ngrok-url/feishu
```

## 💬 使用命令

| 命令 | 说明 |
|------|------|
| `/日报` | 查看今日想法汇总 |
| `/周报` | 查看本周想法汇总 |
| `/月报` | 查看本月想法汇总 |
| `/文档` | 查看今日飞书文档 |
| `/文档 全部` | 查看所有历史文档 |
| `/文档 2026-03-15` | 查看指定日期文档 |
| `/模型` | 查看/切换分类模式 |
| `/帮助` | 查看使用帮助 |

## 📂 文件结构

```
ai-idea-assistant/
├── idea_bot.py          # 主程序
├── feishu_storage_v3.py # 飞书云文档存储模块
├── requirements.txt     # 依赖列表
├── .env.example         # 环境变量模板
├── .gitignore           # Git 忽略文件
├── README.md            # 项目说明
└── ideas/               # 想法存储目录（不提交）
    ├── work.md
    ├── life.md
    └── ...
```

## 🎯 分类说明

- 💼 **工作** - 项目、会议、任务、客户相关
- 🏠 **生活** - 家庭、购物、做饭、家务
- 📚 **学习** - 阅读、课程、知识、技能
- 💡 **灵感** - 创意、点子、思考
- ✅ **待办** - 提醒、要做的事
- 💪 **健康** - 运动、锻炼、饮食、睡眠
- 💰 **财务** - 理财、投资、消费
- 📝 **其他** - 未分类内容

## 🔧 开发

### 添加新命令

在 `handle_command()` 函数中添加：

```python
elif command_lower == "/新命令":
    # 你的逻辑
    send_feishu_text_message(open_id, "标题", "内容")
```

### 切换分类模式

```bash
/模型          # 查看当前模式
/模型 AI       # 切换到 AI 模式
/模型 关键词    # 切换到关键词模式
/模型 自动      # 切换到自动模式
```

## 📝 License

MIT

## 🙏 致谢

- [Anthropic Claude](https://www.anthropic.com/) - AI 分类能力
- [飞书开放平台](https://open.feishu.cn/) - 消息平台
- [ngrok](https://ngrok.com/) - 内网穿透工具

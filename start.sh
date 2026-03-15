#!/bin/bash
# 智能想法记录 Bot 快速启动脚本

echo "========================================"
echo "🤖 智能想法记录 Bot 启动助手"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到 Python 3，请先安装"
    exit 1
fi

echo "✅ Python 版本: $(python3 --version)"
echo ""

# 创建虚拟环境（可选）
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建完成"
fi

# 激活虚拟环境
echo "🔄 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📥 安装依赖..."
pip install -q -r requirements.txt
echo "✅ 依赖安装完成"
echo ""

# 检查配置文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 配置文件"
    echo "📝 复制配置模板..."
    cp .env.example .env
    echo "✅ 请编辑 .env 文件，填入你的 API Key"
    echo "   vim .env"
    echo ""
    read -p "按回车继续..."
fi

# 创建想法目录
mkdir -p ideas

# 启动服务
echo "🚀 启动 Bot 服务..."
echo ""
python3 idea_bot.py

FROM python:3.10-slim

LABEL maintainer="idea-bot"
LABEL description="智能想法记录 Bot"

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用文件
COPY idea_bot.py .
COPY .env .

# 创建数据目录
RUN mkdir -p /app/ideas

# 暴露端口
EXPOSE 5000

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import requests; requests.get('http://localhost:5000/health')"

# 启动服务
CMD ["python", "idea_bot.py"]

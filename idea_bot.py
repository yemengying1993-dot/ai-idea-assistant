#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能想法记录 Bot
- 接收企业微信/飞书消息
- AI 自动分类
- 保存到 Markdown 文档
"""

import os
import json
import hashlib
import hmac
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify
import anthropic
import requests  # 新增：用于调用飞书API

# 时区支持
try:
    from pytz import timezone
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Shanghai")
    tz = timezone(TIMEZONE)
    TIMEZONE_AVAILABLE = True
    print(f"🌍 时区设置: {TIMEZONE}")
except ImportError:
    TIMEZONE_AVAILABLE = False
    tz = None
    print("⚠️  pytz 未安装，将使用服务器本地时间")

# 加载 .env 文件（仅本地开发使用，生产环境通过平台环境变量配置）
try:
    from dotenv import load_dotenv
    if os.path.exists('.env'):
        load_dotenv()
except (ImportError, FileNotFoundError):
    # 生产环境不需要 .env 文件
    pass

# 导入企业微信加密模块
try:
    from wechat_crypto import WXBizMsgCrypt
    WECHAT_CRYPTO_AVAILABLE = True
except ImportError:
    WECHAT_CRYPTO_AVAILABLE = False
    print("警告: wechat_crypto 模块未找到，企业微信验证可能失败")

# 导入飞书云文档存储模块
try:
    from feishu_storage_v3 import (
        save_to_feishu,
        read_daily_summary,
        list_today_docs,
        list_all_docs,
        list_docs_by_date
    )
    FEISHU_STORAGE_AVAILABLE = True
    print("✅ 飞书云文档存储模块已加载（V3 - 简化版，无需文件夹）")
except ImportError:
    FEISHU_STORAGE_AVAILABLE = False
    print("⚠️  飞书云文档存储模块未找到，将只使用本地存储")

app = Flask(__name__)

# ========== 配置 ==========
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # Claude API Key
IDEAS_DIR = Path("ideas")  # 想法保存目录
IDEAS_DIR.mkdir(exist_ok=True)

# 企业微信配置（从环境变量读取，用于加密验证）
WEWORK_TOKEN = os.getenv("WEWORK_TOKEN", "")
WEWORK_ENCODING_AES_KEY = os.getenv("WEWORK_ENCODING_AES_KEY", "")
WEWORK_CORP_ID = os.getenv("WEWORK_CORP_ID", "")

# 飞书配置
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# 飞书 Token 缓存
feishu_token_cache = {"token": None, "expire_time": 0}

# 时区感知的时间获取函数
def get_current_time():
    """获取当前时间（考虑时区）
    
    Returns:
        datetime: 当前时间对象
    """
    if TIMEZONE_AVAILABLE and tz:
        return datetime.now(tz)
    else:
        return datetime.now()

# 消息去重（防止重复处理同一条消息）
processed_messages = set()
MAX_PROCESSED_MESSAGES = 10000  # 最多缓存1万条消息ID

# 分类模式控制
CLASSIFIER_MODE = "auto"  # auto: 自动 / ai: 强制AI / keyword: 强制关键词

def is_message_processed(message_id):
    """检查消息是否已处理"""
    if message_id in processed_messages:
        return True
    
    # 添加到已处理列表
    processed_messages.add(message_id)
    
    # 如果缓存太大，清理一半
    if len(processed_messages) > MAX_PROCESSED_MESSAGES:
        # 清理前一半（最旧的）
        to_remove = list(processed_messages)[:MAX_PROCESSED_MESSAGES // 2]
        for msg_id in to_remove:
            processed_messages.discard(msg_id)
    
    return False


def get_classifier_status():
    """获取当前分类器状态"""
    if CLASSIFIER_MODE == "keyword":
        return {
            "mode": "keyword",
            "name": "关键词匹配",
            "emoji": "📝",
            "can_use_ai": bool(ANTHROPIC_API_KEY),
            "description": "使用关键词匹配进行分类"
        }
    elif CLASSIFIER_MODE == "ai":
        if ANTHROPIC_API_KEY:
            return {
                "mode": "ai",
                "name": "Claude AI",
                "emoji": "🤖",
                "can_use_ai": True,
                "description": "使用 Claude AI 智能分类"
            }
        else:
            return {
                "mode": "keyword",
                "name": "关键词匹配（无API Key）",
                "emoji": "⚠️",
                "can_use_ai": False,
                "description": "未配置API Key，降级为关键词匹配"
            }
    else:  # auto
        if ANTHROPIC_API_KEY:
            return {
                "mode": "ai",
                "name": "Claude AI（自动）",
                "emoji": "🤖",
                "can_use_ai": True,
                "description": "自动模式：使用 Claude AI"
            }
        else:
            return {
                "mode": "keyword",
                "name": "关键词匹配（自动）",
                "emoji": "📝",
                "can_use_ai": False,
                "description": "自动模式：未配置API，使用关键词匹配"
            }


def set_classifier_mode(mode):
    """设置分类模式"""
    global CLASSIFIER_MODE
    if mode in ["auto", "ai", "keyword"]:
        CLASSIFIER_MODE = mode
        return True
    return False

# 分类定义
CATEGORIES = {
    "work": {"name": "工作", "emoji": "💼", "file": "work.md", "keywords": ["工作", "项目", "会议", "任务", "客户", "业绩"]},
    "life": {"name": "生活", "emoji": "🏠", "file": "life.md", "keywords": ["生活", "家庭", "购物", "做饭", "家务"]},
    "study": {"name": "学习", "emoji": "📚", "file": "study.md", "keywords": ["学习", "阅读", "课程", "知识", "技能"]},
    "inspiration": {"name": "灵感", "emoji": "💡", "file": "inspiration.md", "keywords": ["想法", "创意", "点子", "灵感", "思考"]},
    "todo": {"name": "待办", "emoji": "✅", "file": "todo.md", "keywords": ["待办", "提醒", "要做", "记得", "别忘"]},
    "health": {"name": "健康", "emoji": "💪", "file": "health.md", "keywords": ["健康", "运动", "锻炼", "饮食", "睡眠"]},
    "finance": {"name": "财务", "emoji": "💰", "file": "finance.md", "keywords": ["理财", "投资", "股票", "消费", "预算"]},
    "other": {"name": "其他", "emoji": "📝", "file": "other.md", "keywords": []}
}


def classify_idea_with_ai(content: str) -> str:
    """使用 Claude AI 对想法进行分类"""
    global CLASSIFIER_MODE
    
    # 检查模式设置
    if CLASSIFIER_MODE == "keyword":
        print("📝 使用关键词匹配分类（模式：强制关键词）")
        return classify_idea_simple(content)
    
    if not ANTHROPIC_API_KEY:
        print("⚠️  未配置 ANTHROPIC_API_KEY，使用关键词匹配分类")
        return classify_idea_simple(content)
    
    if CLASSIFIER_MODE == "ai" or CLASSIFIER_MODE == "auto":
        print("🤖 使用 Claude AI 进行智能分类...")
        
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            
            categories_desc = "\n".join([
                f"- {cat_id}（{info['name']}）: {', '.join(info['keywords']) if info['keywords'] else '其他内容'}"
                for cat_id, info in CATEGORIES.items()
            ])
            
            prompt = f"""请将以下想法分类到最合适的类别。只返回类别ID，不要其他文字。

可选类别：
{categories_desc}

想法内容：
{content}

类别ID："""

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            
            category = message.content[0].text.strip().lower()
            
            # 验证返回的类别是否有效
            if category in CATEGORIES:
                print(f"✅ AI 分类成功: {category} ({CATEGORIES[category]['emoji']} {CATEGORIES[category]['name']})")
                return category
            else:
                print(f"⚠️  AI 返回了无效分类: {category}，回退到关键词匹配")
                return classify_idea_simple(content)
                
        except Exception as e:
            print(f"❌ AI 分类失败: {e}")
            print("⚠️  回退到关键词匹配分类")
            return classify_idea_simple(content)
    
    # 默认使用关键词匹配
    return classify_idea_simple(content)


def classify_idea_simple(content: str) -> str:
    """简单的关键词匹配分类（备用方案）"""
    content_lower = content.lower()
    
    # 按优先级匹配
    for cat_id, info in CATEGORIES.items():
        if cat_id == "other":
            continue
        for keyword in info["keywords"]:
            if keyword in content_lower:
                print(f"📝 关键词匹配成功: '{keyword}' → {cat_id} ({info['emoji']} {info['name']})")
                return cat_id
    
    print(f"📝 未匹配到关键词，使用默认分类: other")
    return "other"


def get_feishu_tenant_access_token():
    """获取飞书 tenant_access_token"""
    global feishu_token_cache
    
    # 检查缓存是否有效
    import time
    if feishu_token_cache["token"] and time.time() < feishu_token_cache["expire_time"]:
        return feishu_token_cache["token"]
    
    # 获取新 token
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("⚠️  未配置飞书 APP_ID 或 APP_SECRET")
        return None
    
    try:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET
        }
        response = requests.post(url, json=data)
        result = response.json()
        
        if result.get("code") == 0:
            token = result.get("tenant_access_token")
            expire = result.get("expire", 7200)
            
            # 缓存 token（提前5分钟过期）
            feishu_token_cache["token"] = token
            feishu_token_cache["expire_time"] = time.time() + expire - 300
            
            return token
        else:
            print(f"❌ 获取飞书 token 失败: {result}")
            return None
    except Exception as e:
        print(f"❌ 获取飞书 token 异常: {e}")
        return None


def generate_daily_report():
    """生成日报（优先从飞书云文档读取）"""
    today = get_current_time()
    date_str = today.strftime("%Y-%m-%d")
    
    # 1️⃣ 尝试从飞书汇总文档读取
    if FEISHU_STORAGE_AVAILABLE:
        token = get_feishu_tenant_access_token()
        if token:
            try:
                feishu_content = read_daily_summary(token, date_str)
                if feishu_content:
                    print("📊 从飞书云文档生成日报")
                    return f"📅 {date_str} 每日想法汇总\n\n{feishu_content}"
            except Exception as e:
                print(f"⚠️  从飞书读取日报失败: {e}")
    
    # 2️⃣ 从本地文件读取（备用方案）
    print("📊 从本地文件生成日报")
    
    # 统计各分类数量
    stats = {cat: 0 for cat in CATEGORIES.keys()}
    category_ideas = {cat: [] for cat in CATEGORIES.keys()}
    
    # 读取所有分类文件统计今日想法
    for category, info in CATEGORIES.items():
        category_file = IDEAS_DIR / info["file"]
        if category_file.exists():
            with open(category_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                i = 0
                while i < len(lines):
                    line = lines[i]
                    # 检查是否是今天的记录（格式：## 2026-03-15 18:27:05）
                    if line.startswith("##") and date_str in line:
                        stats[category] += 1
                        # 读取下一行作为想法内容
                        if i + 1 < len(lines):
                            content = lines[i + 1].strip()
                            if content:  # 确保不是空行
                                category_ideas[category].append(content)
                    i += 1
    
    total = sum(stats.values())
    
    if total == 0:
        return f"📅 {date_str}\n\n今天还没有记录任何想法哦！\n\n💡 快发送一条想法试试吧~"
    
    # 生成报告
    report = f"📅 {date_str} 每日想法汇总\n\n"
    report += f"📊 今日统计\n"
    report += f"• 总计：{total} 条想法\n"
    
    for category, count in stats.items():
        if count > 0:
            emoji = CATEGORIES[category]["emoji"]
            name = CATEGORIES[category]["name"]
            report += f"• {emoji} {name}：{count} 条\n"
    
    report += f"\n📝 今日亮点\n"
    for category, ideas in category_ideas.items():
        if ideas:
            emoji = CATEGORIES[category]["emoji"]
            name = CATEGORIES[category]["name"]
            report += f"\n{emoji} {name} ({len(ideas)}条)\n"
            for idea in ideas[:5]:  # 最多显示5条
                report += f"• {idea}\n"
    
    return report


def generate_weekly_report():
    """生成周报（优先从飞书云文档读取）"""
    today = get_current_time()
    # 获取本周一
    monday = today - timedelta(days=today.weekday())
    
    # 1️⃣ 尝试从飞书汇总文档读取本周数据
    if FEISHU_STORAGE_AVAILABLE:
        token = get_feishu_tenant_access_token()
        if token:
            try:
                week_content = []
                for i in range(7):
                    day = monday + timedelta(days=i)
                    if day > today:
                        break
                    date_str = day.strftime("%Y-%m-%d")
                    daily_content = read_daily_summary(token, date_str)
                    if daily_content:
                        week_content.append(f"\n📅 {date_str}\n{daily_content}")
                
                if week_content:
                    print("📊 从飞书云文档生成周报")
                    week_start = monday.strftime("%m/%d")
                    week_end = today.strftime("%m/%d")
                    return f"📅 本周想法汇总 ({week_start} - {week_end})\n\n" + "\n".join(week_content)
            except Exception as e:
                print(f"⚠️  从飞书读取周报失败: {e}")
    
    # 2️⃣ 从本地文件读取（备用方案）
    print("📊 从本地文件生成周报")
    
    # 统计本周想法
    stats = {cat: 0 for cat in CATEGORIES.keys()}
    category_ideas = {cat: [] for cat in CATEGORIES.keys()}
    
    # 遍历本周每一天
    week_dates = set()
    for i in range(7):
        day = monday + timedelta(days=i)
        if day > today:
            break
        week_dates.add(day.strftime("%Y-%m-%d"))
    
    # 读取各分类文件
    for category, info in CATEGORIES.items():
        category_file = IDEAS_DIR / info["file"]
        if category_file.exists():
            with open(category_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                i = 0
                while i < len(lines):
                    line = lines[i]
                    # 检查是否是本周的记录
                    if line.startswith("##"):
                        for date_str in week_dates:
                            if date_str in line:
                                stats[category] += 1
                                # 读取下一行作为想法内容
                                if i + 1 < len(lines):
                                    content = lines[i + 1].strip()
                                    if content:
                                        category_ideas[category].append(content)
                                break
                    i += 1
    
    total = sum(stats.values())
    
    if total == 0:
        week_start = monday.strftime("%m/%d")
        week_end = today.strftime("%m/%d")
        return f"📅 本周 ({week_start} - {week_end})\n\n本周还没有记录任何想法哦！\n\n💡 快发送一条想法试试吧~"
    
    # 生成报告
    week_start = monday.strftime("%m/%d")
    week_end = today.strftime("%m/%d")
    report = f"📅 本周想法汇总 ({week_start} - {week_end})\n\n"
    report += f"📊 本周统计\n"
    report += f"• 总计：{total} 条想法\n"
    
    for category, count in stats.items():
        if count > 0:
            emoji = CATEGORIES[category]["emoji"]
            name = CATEGORIES[category]["name"]
            report += f"• {emoji} {name}：{count} 条\n"
    
    report += f"\n🌟 本周精选\n"
    for category, ideas in category_ideas.items():
        if ideas:
            emoji = CATEGORIES[category]["emoji"]
            name = CATEGORIES[category]["name"]
            report += f"\n{emoji} {name} ({len(ideas)}条)\n"
            # 显示最近的几条
            for idea in ideas[-5:]:  # 最多显示最近5条
                report += f"• {idea}\n"
    
    return report


def generate_monthly_report():
    """生成月报"""
    today = get_current_time()
    year_month = today.strftime("%Y-%m")
    
    # 统计本月想法
    stats = {cat: 0 for cat in CATEGORIES.keys()}
    category_ideas = {cat: [] for cat in CATEGORIES.keys()}
    
    # 读取各分类文件
    for category, info in CATEGORIES.items():
        category_file = IDEAS_DIR / info["file"]
        if category_file.exists():
            with open(category_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                i = 0
                while i < len(lines):
                    line = lines[i]
                    # 检查是否是本月的记录
                    if line.startswith("##") and year_month in line:
                        stats[category] += 1
                        # 读取下一行作为想法内容
                        if i + 1 < len(lines):
                            content = lines[i + 1].strip()
                            if content:
                                category_ideas[category].append(content)
                    i += 1
    
    total = sum(stats.values())
    
    if total == 0:
        month_name = today.strftime("%Y年%m月")
        return f"📅 {month_name}\n\n本月还没有记录任何想法哦！\n\n💡 快发送一条想法试试吧~"
    
    # 生成报告
    month_name = today.strftime("%Y年%m月")
    report = f"📅 {month_name}想法汇总\n\n"
    report += f"📊 本月统计\n"
    report += f"• 总计：{total} 条想法\n"
    
    for category, count in stats.items():
        if count > 0:
            emoji = CATEGORIES[category]["emoji"]
            name = CATEGORIES[category]["name"]
            percentage = (count / total * 100) if total > 0 else 0
            report += f"• {emoji} {name}：{count} 条 ({percentage:.1f}%)\n"
    
    report += f"\n💎 本月精华\n"
    for category, ideas in category_ideas.items():
        if ideas:
            emoji = CATEGORIES[category]["emoji"]
            name = CATEGORIES[category]["name"]
            report += f"\n{emoji} {name} ({len(ideas)}条)\n"
            # 显示最近的几条
            for idea in ideas[-3:]:  # 月报只显示最近3条
                report += f"• {idea}\n"
    
    return report


def handle_command(command: str, open_id: str):
    """处理命令"""
    command_lower = command.lower().strip()
    
    print(f"🎯 处理命令: {command_lower}")
    
    if command_lower == "/日报" or command_lower == "/daily":
        report = generate_daily_report()
        send_feishu_text_message(open_id, "📅 每日想法汇总", report)
    
    elif command_lower == "/周报" or command_lower == "/weekly":
        report = generate_weekly_report()
        send_feishu_text_message(open_id, "📅 每周想法汇总", report)
    
    elif command_lower == "/月报" or command_lower == "/monthly":
        report = generate_monthly_report()
        send_feishu_text_message(open_id, "📅 每月想法汇总", report)
    
    elif command_lower.startswith("/文档") or command_lower.startswith("/docs"):
        # 解析参数
        parts = command.strip().split()
        
        if FEISHU_STORAGE_AVAILABLE:
            token = get_feishu_tenant_access_token()
            if not token:
                send_feishu_text_message(open_id, "错误", "⚠️ 无法获取飞书 token")
                return
            
            # 情况1: /文档 全部
            if len(parts) > 1 and parts[1] in ["全部", "all", "历史"]:
                docs_by_date = list_all_docs(token)
                
                if docs_by_date:
                    # 按日期倒序排列
                    sorted_dates = sorted(docs_by_date.keys(), reverse=True)
                    
                    message = f"📚 全部文档 (共 {len(sorted_dates)} 天)\n\n"
                    
                    for date_str in sorted_dates:
                        docs = docs_by_date[date_str]
                        message += f"📅 {date_str} ({len(docs)}个文档)\n"
                        
                        for doc in docs:
                            message += f"  {doc['emoji']} {doc['category']}\n"
                            message += f"  🔗 {doc['url']}\n"
                        
                        message += "\n"
                    
                    message += "💡 提示：点击链接直接打开文档"
                    send_feishu_text_message(open_id, "📚 全部文档", message)
                else:
                    send_feishu_text_message(open_id, "📚 全部文档", 
                        "还没有创建任何文档哦！\n\n💡 发送一条想法试试~")
            
            # 情况2: /文档 2026-03-15（指定日期）
            elif len(parts) > 1:
                date_str = parts[1]
                
                # 验证日期格式
                try:
                    from datetime import datetime
                    datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    send_feishu_text_message(open_id, "❌ 格式错误", 
                        f"日期格式不正确: {date_str}\n\n请使用格式: YYYY-MM-DD\n例如: /文档 2026-03-15")
                    return
                
                docs = list_docs_by_date(token, date_str)
                
                if docs:
                    message = f"📚 {date_str} 的文档\n\n"
                    
                    for doc in docs:
                        message += f"{doc['emoji']} {doc['category']}\n"
                        message += f"🔗 {doc['url']}\n\n"
                    
                    message += "💡 提示：点击链接直接打开文档"
                    send_feishu_text_message(open_id, f"📚 {date_str} 的文档", message)
                else:
                    send_feishu_text_message(open_id, f"📚 {date_str} 的文档", 
                        f"{date_str} 没有创建任何文档")
            
            # 情况3: /文档（今天的文档）
            else:
                docs = list_today_docs(token)
                
                if docs:
                    today = get_current_time().strftime("%Y-%m-%d")
                    message = f"📚 今日文档 ({today})\n\n"
                    
                    for doc in docs:
                        message += f"{doc['emoji']} {doc['category']}\n"
                        message += f"🔗 {doc['url']}\n\n"
                    
                    message += "💡 提示：\n"
                    message += "• 点击链接直接打开文档\n"
                    message += "• /文档 全部 - 查看所有历史文档\n"
                    message += "• /文档 2026-03-15 - 查看指定日期文档"
                    
                    send_feishu_text_message(open_id, "📚 今日文档", message)
                else:
                    send_feishu_text_message(open_id, "📚 今日文档", 
                        f"今天还没有创建任何文档哦！\n\n💡 发送一条想法试试~")
        else:
            send_feishu_text_message(open_id, "提示", "⚠️ 飞书云文档功能未启用")
    
    elif command_lower.startswith("/模型") or command_lower.startswith("/model"):
        # 处理模型切换命令
        # 检查是否带参数
        parts = command.strip().split()
        if len(parts) == 1:
            # 查询当前模式
            status = get_classifier_status()
            mode_info = f"""🤖 当前分类模式

{status['emoji']} 模式: {status['name']}
{status['description']}

📝 可用模式：
• AI模式 - 使用 Claude AI 智能分类
• 关键词模式 - 使用关键词匹配分类
• 自动模式 - 有API用AI，无API用关键词

💡 切换方式：
/模型 AI - 切换到AI模式
/模型 关键词 - 切换到关键词模式
/模型 自动 - 切换到自动模式"""
            
            if not status['can_use_ai']:
                mode_info += "\n\n⚠️  提示：未配置 ANTHROPIC_API_KEY，无法使用AI模式"
            
            send_feishu_text_message(open_id, "🤖 分类模式", mode_info)
        else:
            # 切换模式
            mode_param = parts[1].lower()
            if mode_param in ["ai", "ai模式", "智能"]:
                if set_classifier_mode("ai"):
                    status = get_classifier_status()
                    send_feishu_text_message(open_id, "✅ 模式已切换", 
                        f"已切换到：{status['emoji']} {status['name']}\n\n{status['description']}")
                    print(f"✅ 分类模式已切换: AI模式")
            elif mode_param in ["keyword", "关键词", "关键词模式"]:
                if set_classifier_mode("keyword"):
                    status = get_classifier_status()
                    send_feishu_text_message(open_id, "✅ 模式已切换", 
                        f"已切换到：{status['emoji']} {status['name']}\n\n{status['description']}")
                    print(f"✅ 分类模式已切换: 关键词模式")
            elif mode_param in ["auto", "自动", "自动模式"]:
                if set_classifier_mode("auto"):
                    status = get_classifier_status()
                    send_feishu_text_message(open_id, "✅ 模式已切换", 
                        f"已切换到：{status['emoji']} {status['name']}\n\n{status['description']}")
                    print(f"✅ 分类模式已切换: 自动模式")
            else:
                send_feishu_text_message(open_id, "❌ 参数错误", 
                    f"不支持的模式: {mode_param}\n\n请使用: /模型 AI 或 /模型 关键词 或 /模型 自动")
    
    elif command_lower == "/帮助" or command_lower == "/help":
        status = get_classifier_status()
        help_text = f"""🤖 智能想法记录助手

📝 使用方法
直接发送消息即可自动记录并分类

🎯 支持的命令
• /文档 - 查看今日文档
• /文档 全部 - 查看所有历史文档
• /文档 2026-03-15 - 查看指定日期文档
• /日报 - 查看今日想法汇总
• /周报 - 查看本周想法汇总
• /月报 - 查看本月想法汇总
• /模型 - 查看/切换分类模式
• /帮助 - 查看此帮助信息

📂 分类说明
💼 工作 | 🏠 生活 | 📚 学习 | 💡 灵感
✅ 待办 | 💪 健康 | 💰 财务 | 📝 其他

🤖 当前分类模式
{status['emoji']} {status['name']}

💾 数据存储
所有想法都保存为 Markdown 文档
支持全文搜索和版本控制

✨ 快发送一条想法试试吧！"""
        send_feishu_text_message(open_id, "💡 使用帮助", help_text)
    
    else:
        send_feishu_text_message(open_id, "❓ 未知命令", 
            f"不支持的命令: {command}\n\n发送 /帮助 查看所有可用命令")


def send_feishu_text_message(open_id, title, content):
    """发送纯文本消息（用于报告）"""
    token = get_feishu_tenant_access_token()
    if not token:
        return False
    
    try:
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        params = {"receive_id_type": "open_id"}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 构造文本消息卡片
        card_content = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": content
                    }
                }
            ]
        }
        
        data = {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content)
        }
        
        response = requests.post(url, params=params, headers=headers, json=data)
        result = response.json()
        
        if result.get("code") == 0:
            print(f"✅ 飞书报告发送成功")
            return True
        else:
            print(f"❌ 飞书报告发送失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 发送飞书报告异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_feishu_message(open_id, content, category_name, category_emoji, timestamp, doc_url=None):
    """发送飞书消息（带文档链接）"""
    token = get_feishu_tenant_access_token()
    if not token:
        return False
    
    try:
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        params = {"receive_id_type": "open_id"}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 构造消息卡片元素
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content
                }
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"⏰ {timestamp}"
                    }
                ]
            }
        ]
        
        # 添加文档链接（如果有）
        if doc_url:
            elements.append({
                "tag": "hr"
            })
            
            link_element = {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "📄 **查看文档**\n"
                }
            }
            elements.append(link_element)
            
            # 添加按钮：查看今日记录
            actions = [{
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": "📝 查看今日记录"
                },
                "type": "primary",
                "url": doc_url
            }]
            
            elements.append({
                "tag": "action",
                "actions": actions
            })
        
        # 构造完整卡片
        card_content = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"✅ 已记录到【{category_emoji} {category_name}】"
                    },
                    "template": "green"
                },
                "elements": elements
            }
        }
        
        data = {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content["card"])
        }
        
        response = requests.post(url, params=params, headers=headers, json=data)
        result = response.json()
        
        if result.get("code") == 0:
            print(f"✅ 飞书消息发送成功")
            return True
        else:
            print(f"❌ 飞书消息发送失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 发送飞书消息异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def save_idea(category: str, content: str, timestamp: str = None, user_open_id: str = None) -> dict:
    """保存想法（双重存储：本地文件 + 飞书云文档）
    
    Args:
        category: 分类
        content: 内容
        timestamp: 时间戳（可选）
        user_open_id: 用户的 open_id（可选，用于飞书文档自动授权）
    """
    if timestamp is None:
        timestamp = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
    
    date_str = get_current_time().strftime("%Y-%m-%d")
    
    # 每个类别一个文件
    category_file = IDEAS_DIR / f"{category}.md"
    
    cat_info = CATEGORIES.get(category, CATEGORIES["other"])
    
    # 1️⃣ 保存到本地文件
    local_success = False
    try:
        # 构造想法条目
        idea_entry = f"\n### {timestamp}\n{content}\n"
        
        # 如果文件不存在，创建并写入标题
        if not category_file.exists():
            with open(category_file, "w", encoding="utf-8") as f:
                f.write(f"# {cat_info['emoji']} {cat_info['name']}\n\n")
        
        # 追加想法
        with open(category_file, "a", encoding="utf-8") as f:
            f.write(idea_entry)
        
        # 同时保存到总文档（按日期）
        all_ideas_file = IDEAS_DIR / f"all_ideas_{date_str}.md"
        if not all_ideas_file.exists():
            with open(all_ideas_file, "w", encoding="utf-8") as f:
                f.write(f"# 💭 我的想法 - {date_str}\n\n")
        
        with open(all_ideas_file, "a", encoding="utf-8") as f:
            f.write(f"## {cat_info['emoji']} {cat_info['name']} - {timestamp}\n{content}\n\n")
        
        print(f"✅ 本地文件保存成功: {category_file}")
        local_success = True
        
    except Exception as e:
        print(f"⚠️  本地文件保存失败: {e}")
    
    # 2️⃣ 保存到飞书云文档
    feishu_success = False
    doc_url = None
    
    if FEISHU_STORAGE_AVAILABLE:
        token = get_feishu_tenant_access_token()
        if token:
            try:
                result = save_to_feishu(
                    token=token,
                    category=category,
                    content=content,
                    timestamp=timestamp,
                    category_name=cat_info["name"],
                    category_emoji=cat_info["emoji"],
                    user_open_id=user_open_id  # 传递用户ID用于自动授权
                )
                
                if isinstance(result, dict):
                    feishu_success = result.get("success", False)
                    doc_url = result.get("doc_url")
                else:
                    # 兼容旧版本（返回 bool）
                    feishu_success = result
                
                if feishu_success:
                    print(f"✅ 飞书云文档保存成功")
            except Exception as e:
                print(f"⚠️  飞书云文档保存失败: {e}")
    
    return {
        "success": local_success or feishu_success,
        "local_saved": local_success,
        "feishu_saved": feishu_success,
        "category": cat_info["name"],
        "emoji": cat_info["emoji"],
        "file": str(category_file),
        "timestamp": timestamp,
        "doc_url": doc_url
    }


# ========== 企业微信 Webhook ==========
@app.route("/wework", methods=["POST", "GET"])
def wework_webhook():
    """接收企业微信消息（支持加密验证）"""
    try:
        # GET 请求用于验证 URL（企业微信应用配置时）
        if request.method == "GET":
            # 获取验证参数
            msg_signature = request.args.get("msg_signature", "")
            timestamp = request.args.get("timestamp", "")
            nonce = request.args.get("nonce", "")
            echostr = request.args.get("echostr", "")
            
            # 如果有加密配置，使用加密验证
            if WECHAT_CRYPTO_AVAILABLE and WEWORK_TOKEN and WEWORK_ENCODING_AES_KEY and WEWORK_CORP_ID:
                try:
                    wxcpt = WXBizMsgCrypt(WEWORK_TOKEN, WEWORK_ENCODING_AES_KEY, WEWORK_CORP_ID)
                    ret, sEchoStr = wxcpt.verify_url(msg_signature, timestamp, nonce, echostr)
                    
                    if ret == 0:
                        print(f"✅ 企业微信 URL 验证成功")
                        return sEchoStr
                    else:
                        print(f"❌ 企业微信 URL 验证失败: ret={ret}")
                        return "verification failed", 403
                except Exception as e:
                    print(f"❌ 企业微信验证异常: {e}")
                    # 如果加密验证失败，尝试简单模式
                    if echostr:
                        return echostr, 200
                    return "ok", 200
            else:
                # 没有配置加密参数，使用简单模式
                print("⚠️  未配置企业微信加密参数，使用简单验证模式")
                if echostr:
                    return echostr, 200
                return "ok", 200
        
        # POST 请求 - 接收消息
        data = request.get_json()
        
        # 企业微信文本消息格式
        msg_type = data.get("msgtype", "")
        
        if msg_type == "text":
            content = data.get("text", {}).get("content", "").strip()
            
            if not content:
                return jsonify({"msg": "消息为空"})
            
            print(f"📝 收到想法: {content}")
            
            # AI 分类
            category = classify_idea_with_ai(content)
            
            # 保存
            result = save_idea(category, content)
            
            print(f"✅ 已保存到: {result['category']}")
            
            # 回复消息
            return jsonify({
                "msgtype": "text",
                "text": {
                    "content": f"✅ 已记录到【{result['emoji']} {result['category']}】\n\n{content}"
                }
            })
        
        return jsonify({"msg": "不支持的消息类型"})
        
    except Exception as e:
        print(f"❌ 处理企业微信消息失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "msgtype": "text",
            "text": {"content": f"❌ 记录失败: {str(e)}"}
        })


# ========== 飞书 Webhook ==========
@app.route("/feishu", methods=["POST"])
def feishu_webhook():
    """接收飞书消息"""
    try:
        data = request.get_json()
        
        print(f"📥 收到飞书请求: {json.dumps(data, ensure_ascii=False)[:200]}")
        
        # 飞书验证 URL
        if "challenge" in data:
            print("✅ 飞书 URL 验证成功")
            return jsonify({"challenge": data["challenge"]})
        
        # 获取消息内容
        event = data.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        
        # 消息去重：检查 message_id
        message_id = message.get("message_id", "")
        if message_id and is_message_processed(message_id):
            print(f"⚠️  消息已处理过，跳过: {message_id}")
            return jsonify({"code": 0, "msg": "ok"})
        
        # 获取发送者 open_id
        open_id = sender.get("sender_id", {}).get("open_id", "")
        
        # 飞书的字段是 message_type，不是 msg_type
        message_type = message.get("message_type", "")
        
        print(f"📩 收到飞书消息，类型: {message_type}, open_id: {open_id}, msg_id: {message_id}")
        
        # 提取消息内容（支持 text 和 post 类型）
        content = None
        content_str = message.get("content", "{}")
        
        try:
            content_obj = json.loads(content_str)
            
            if message_type == "text":
                # text 类型：{"text": "消息内容"}
                content = content_obj.get("text", "").strip()
            
            elif message_type == "post":
                # post 类型的两种可能结构：
                # 1. {"zh_cn": {"title": "...", "content": [...]}}  (旧版)
                # 2. {"title": "...", "content": [...]}  (新版/当前)
                
                # 尝试从 zh_cn 获取（旧版）
                zh_cn = content_obj.get("zh_cn", {})
                if zh_cn:
                    title = zh_cn.get("title", "").strip()
                    post_content = zh_cn.get("content", [])
                else:
                    # 直接从根级别获取（新版）
                    title = content_obj.get("title", "").strip()
                    post_content = content_obj.get("content", [])
                
                text_parts = []
                
                # 遍历所有段落
                for paragraph in post_content:
                    if isinstance(paragraph, list):
                        # 每个段落是一个数组，包含多个文本元素
                        paragraph_texts = []
                        for element in paragraph:
                            if isinstance(element, dict) and element.get("tag") == "text":
                                text = element.get("text", "").strip()
                                if text:
                                    paragraph_texts.append(text)
                        
                        # 合并段落内的所有文本（用空格连接）
                        if paragraph_texts:
                            text_parts.append("".join(paragraph_texts))
                
                # 组合标题和内容（用换行分隔段落）
                if title and text_parts:
                    content = f"{title}\n\n" + "\n".join(text_parts)
                elif title:
                    content = title
                elif text_parts:
                    content = "\n".join(text_parts)
                
                print(f"📝 post类型消息解析成功: 标题={title[:50] if title else '(无)'}, 段落数={len(text_parts)}")
        
        except Exception as e:
            print(f"⚠️  解析消息内容失败: {e}")
            import traceback
            traceback.print_exc()
            content = content_str.strip()
        
        # 检查内容是否为空
        if not content:
            print("⚠️  消息内容为空")
            return jsonify({"code": 0, "msg": "ok"})
        
        print(f"📝 收到内容: {content[:100]}{'...' if len(content) > 100 else ''}")
        
        # 检查是否是命令
        if content.startswith("/"):
            handle_command(content, open_id)
            return jsonify({"code": 0, "msg": "ok"})
        
        # 普通想法记录
        print(f"🔄 开始处理想法...")
        
        # AI 分类
        try:
            category = classify_idea_with_ai(content)
            print(f"🎯 分类结果: {category}")
        except Exception as e:
            print(f"❌ 分类失败: {e}")
            category = "other"
        
        # 保存
        try:
            result = save_idea(category, content, user_open_id=open_id)
            print(f"✅ 已保存到: {result['category']}")
            print(f"📄 文件路径: {result['file']}")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
            import traceback
            traceback.print_exc()
            # 即使保存失败，也要回复用户
            send_feishu_text_message(open_id, "❌ 保存失败", f"抱歉，保存失败: {str(e)}")
            return jsonify({"code": 0, "msg": "ok"})
        
        # 主动发送回复消息
        if open_id:
            send_feishu_message(
                open_id=open_id,
                content=content[:1000] if len(content) > 1000 else content,  # 限制显示长度
                category_name=result['category'],
                category_emoji=result['emoji'],
                timestamp=result['timestamp'],
                doc_url=result.get('doc_url')
            )
        else:
            print("⚠️  未获取到 open_id，无法回复")
        
        # 返回成功（飞书要求）
        return jsonify({"code": 0, "msg": "ok"})
        
    except Exception as e:
        print(f"❌ 处理飞书消息失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"code": 0, "msg": "ok"})


# ========== 健康检查 ==========
@app.route("/health", methods=["GET"])
def health_check():
    """健康检查接口"""
    return jsonify({
        "status": "ok",
        "ai_enabled": bool(ANTHROPIC_API_KEY),
        "ideas_dir": str(IDEAS_DIR.absolute()),
        "categories": len(CATEGORIES)
    })


# ========== 查看统计 ==========
@app.route("/stats", methods=["GET"])
def get_stats():
    """查看想法统计"""
    stats = {}
    total = 0
    
    for cat_id, cat_info in CATEGORIES.items():
        file_path = IDEAS_DIR / f"{cat_id}.md"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                count = f.read().count("### ")
            stats[cat_info["name"]] = count
            total += count
        else:
            stats[cat_info["name"]] = 0
    
    return jsonify({
        "total": total,
        "by_category": stats
    })


if __name__ == "__main__":
    # 支持自定义端口
    PORT = int(os.getenv("PORT", 5004))  # 默认改为 5001，避免与 macOS AirPlay 冲突
    
    print("=" * 60)
    print("🤖 智能想法记录 Bot 启动中...")
    print("=" * 60)
    print(f"📁 想法保存目录: {IDEAS_DIR.absolute()}")
    
    # 显示分类模式
    status = get_classifier_status()
    print(f"{status['emoji']} 分类模式: {status['name']}")
    if ANTHROPIC_API_KEY:
        print(f"   ✅ Claude API Key: {ANTHROPIC_API_KEY[:20]}...{ANTHROPIC_API_KEY[-5:]}")
    else:
        print(f"   ⚠️  未配置 ANTHROPIC_API_KEY")
    print(f"   当前模式: {CLASSIFIER_MODE}")
    print(f"   说明: {status['description']}")
    
    # 飞书配置状态
    feishu_status = "✅ 已配置" if (FEISHU_APP_ID and FEISHU_APP_SECRET) else "❌ 未配置"
    print(f"📱 飞书配置: {feishu_status}")
    if FEISHU_APP_ID and FEISHU_APP_SECRET:
        print(f"   App ID: {FEISHU_APP_ID[:20]}...")
    
    # 企业微信配置状态
    wework_status = "✅ 已配置" if (WEWORK_TOKEN and WEWORK_ENCODING_AES_KEY and WEWORK_CORP_ID) else "❌ 未配置"
    print(f"🔐 企业微信加密: {wework_status}")
    if WEWORK_TOKEN and WEWORK_ENCODING_AES_KEY and WEWORK_CORP_ID:
        print(f"   Token: {WEWORK_TOKEN[:10]}...")
        print(f"   CorpID: {WEWORK_CORP_ID[:10]}...")
    
    print(f"🌐 访问地址:")
    print(f"   - 企业微信: http://0.0.0.0:{PORT}/wework")
    print(f"   - 飞书: http://0.0.0.0:{PORT}/feishu")
    print(f"   - 健康检查: http://0.0.0.0:{PORT}/health")
    print(f"   - 统计数据: http://0.0.0.0:{PORT}/stats")
    print(f"💡 提示: macOS 用户如需使用 5000 端口，请关闭系统设置中的 AirPlay Receiver")
    print(f"💡 命令: 发送 /模型 查看或切换分类模式")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=PORT, debug=False)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
想法汇总报告生成器
- 按周/月生成汇总报告
- 统计各类别想法数量
- 生成可视化图表
"""

import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import re

IDEAS_DIR = Path("ideas")

CATEGORIES = {
    "work": {"name": "工作", "emoji": "💼"},
    "life": {"name": "生活", "emoji": "🏠"},
    "study": {"name": "学习", "emoji": "📚"},
    "inspiration": {"name": "灵感", "emoji": "💡"},
    "todo": {"name": "待办", "emoji": "✅"},
    "health": {"name": "健康", "emoji": "💪"},
    "finance": {"name": "财务", "emoji": "💰"},
    "other": {"name": "其他", "emoji": "📝"}
}


def parse_ideas_from_file(file_path: Path) -> list:
    """从文件中解析想法"""
    ideas = []
    
    if not file_path.exists():
        return ideas
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用正则提取 ### 时间戳和内容
    pattern = r'### (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\n(.*?)(?=\n###|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    for timestamp_str, idea_content in matches:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        ideas.append({
            "timestamp": timestamp,
            "content": idea_content.strip()
        })
    
    return ideas


def filter_by_date_range(ideas: list, start_date: datetime, end_date: datetime) -> list:
    """按日期范围过滤"""
    return [
        idea for idea in ideas
        if start_date <= idea["timestamp"] <= end_date
    ]


def generate_weekly_report(week_offset: int = 0):
    """生成周报"""
    today = datetime.now()
    
    # 计算本周的周一和周日
    weekday = today.weekday()
    start_of_week = today - timedelta(days=weekday + week_offset * 7)
    end_of_week = start_of_week + timedelta(days=6)
    
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = end_of_week.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return generate_report(start_of_week, end_of_week, f"周报_{start_of_week.strftime('%Y年第%W周')}")


def generate_monthly_report(month_offset: int = 0):
    """生成月报"""
    today = datetime.now()
    
    # 计算目标月份
    target_month = today.month + month_offset
    target_year = today.year
    
    while target_month < 1:
        target_month += 12
        target_year -= 1
    while target_month > 12:
        target_month -= 12
        target_year += 1
    
    # 月初和月末
    start_of_month = datetime(target_year, target_month, 1)
    
    if target_month == 12:
        end_of_month = datetime(target_year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end_of_month = datetime(target_year, target_month + 1, 1) - timedelta(seconds=1)
    
    return generate_report(start_of_month, end_of_month, f"月报_{start_of_month.strftime('%Y年%m月')}")


def generate_report(start_date: datetime, end_date: datetime, report_name: str):
    """生成汇总报告"""
    print(f"📊 正在生成报告: {report_name}")
    print(f"📅 时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print()
    
    # 收集所有分类的想法
    all_ideas_by_category = defaultdict(list)
    total_count = 0
    
    for cat_id, cat_info in CATEGORIES.items():
        file_path = IDEAS_DIR / f"{cat_id}.md"
        all_ideas = parse_ideas_from_file(file_path)
        filtered_ideas = filter_by_date_range(all_ideas, start_date, end_date)
        
        if filtered_ideas:
            all_ideas_by_category[cat_id] = filtered_ideas
            total_count += len(filtered_ideas)
    
    if total_count == 0:
        print("❌ 该时间段内没有记录任何想法")
        return None
    
    # 生成报告文件
    report_file = IDEAS_DIR / f"{report_name}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        # 标题
        f.write(f"# 💭 {report_name}\n\n")
        f.write(f"**时间范围**: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}\n\n")
        f.write(f"**想法总数**: {total_count} 条\n\n")
        f.write("---\n\n")
        
        # 统计概览
        f.write("## 📊 分类统计\n\n")
        for cat_id, ideas in sorted(all_ideas_by_category.items(), key=lambda x: len(x[1]), reverse=True):
            cat_info = CATEGORIES[cat_id]
            count = len(ideas)
            percentage = count / total_count * 100
            f.write(f"- {cat_info['emoji']} **{cat_info['name']}**: {count} 条 ({percentage:.1f}%)\n")
        f.write("\n---\n\n")
        
        # 详细内容
        f.write("## 📝 详细内容\n\n")
        for cat_id, ideas in all_ideas_by_category.items():
            cat_info = CATEGORIES[cat_id]
            f.write(f"### {cat_info['emoji']} {cat_info['name']} ({len(ideas)} 条)\n\n")
            
            for idea in sorted(ideas, key=lambda x: x['timestamp']):
                f.write(f"**{idea['timestamp'].strftime('%m-%d %H:%M')}**\n")
                f.write(f"{idea['content']}\n\n")
            
            f.write("\n")
    
    print(f"✅ 报告已生成: {report_file}")
    print()
    
    # 打印统计信息
    print("📊 统计概览:")
    for cat_id, ideas in sorted(all_ideas_by_category.items(), key=lambda x: len(x[1]), reverse=True):
        cat_info = CATEGORIES[cat_id]
        count = len(ideas)
        percentage = count / total_count * 100
        bar_length = int(percentage / 2)
        bar = "█" * bar_length
        print(f"  {cat_info['emoji']} {cat_info['name']:6s} {count:3d} 条 {bar} {percentage:.1f}%")
    
    return report_file


if __name__ == "__main__":
    print("=" * 60)
    print("📋 想法汇总报告生成器")
    print("=" * 60)
    print()
    print("请选择报告类型:")
    print("  1. 本周周报")
    print("  2. 上周周报")
    print("  3. 本月月报")
    print("  4. 上月月报")
    print("  5. 自定义时间范围")
    print()
    
    choice = input("请输入选项 (1-5): ").strip()
    print()
    
    if choice == "1":
        generate_weekly_report(0)
    elif choice == "2":
        generate_weekly_report(-1)
    elif choice == "3":
        generate_monthly_report(0)
    elif choice == "4":
        generate_monthly_report(-1)
    elif choice == "5":
        start_str = input("开始日期 (YYYY-MM-DD): ").strip()
        end_str = input("结束日期 (YYYY-MM-DD): ").strip()
        
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            generate_report(start_date, end_date, f"自定义报告_{start_str}_至_{end_str}")
        except ValueError:
            print("❌ 日期格式错误，请使用 YYYY-MM-DD 格式")
    else:
        print("❌ 无效选项")

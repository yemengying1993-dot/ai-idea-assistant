# 在 idea_bot.py 中的修改部分

# ========== 导入飞书云文档存储模块 ==========
try:
    from feishu_storage import save_to_feishu, read_daily_summary, FEISHU_FOLDERS, FEISHU_FOLDER_SUMMARY
    FEISHU_STORAGE_AVAILABLE = True
    print("✅ 飞书云文档存储模块已加载")
except ImportError:
    FEISHU_STORAGE_AVAILABLE = False
    print("⚠️  飞书云文档存储模块未找到，将只使用本地存储")


# ========== 修改后的 save_idea 函数 ==========
def save_idea(category: str, content: str, timestamp: str = None) -> dict:
    """保存想法（双重存储：本地文件 + 飞书云文档）
    
    Args:
        category: 分类 ID
        content: 想法内容
        timestamp: 时间戳
        
    Returns:
        dict: 保存结果
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    cat_info = CATEGORIES.get(category, CATEGORIES["other"])
    
    # 1️⃣ 保存到本地文件（Railway Volume 或本地开发）
    category_file = IDEAS_DIR / cat_info["file"]
    local_success = False
    
    try:
        if not category_file.exists():
            with open(category_file, "w", encoding="utf-8") as f:
                f.write(f"# {cat_info['emoji']} {cat_info['name']}\n\n")
        
        with open(category_file, "a", encoding="utf-8") as f:
            f.write(f"## {timestamp}\n{content}\n\n")
        
        # 同时保存到每日汇总
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
    
    if FEISHU_STORAGE_AVAILABLE:
        token = get_feishu_tenant_access_token()
        if token:
            try:
                feishu_success = save_to_feishu(
                    token=token,
                    category=category,
                    content=content,
                    timestamp=timestamp,
                    category_name=cat_info["name"]
                )
            except Exception as e:
                print(f"⚠️  飞书云文档保存失败: {e}")
    
    # 返回结果
    return {
        "success": local_success or feishu_success,
        "local_saved": local_success,
        "feishu_saved": feishu_success,
        "category": cat_info["name"],
        "emoji": cat_info["emoji"],
        "file": str(category_file),
        "timestamp": timestamp
    }


# ========== 修改后的日报函数（支持从飞书读取）==========
def generate_daily_report(use_feishu=True):
    """生成日报
    
    Args:
        use_feishu: 是否优先从飞书读取
        
    Returns:
        str: 日报内容
    """
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    
    # 1. 尝试从飞书汇总文档读取
    if use_feishu and FEISHU_STORAGE_AVAILABLE and FEISHU_FOLDER_SUMMARY:
        token = get_feishu_tenant_access_token()
        if token:
            feishu_content = read_daily_summary(token, date_str)
            if feishu_content:
                print("📊 从飞书云文档生成日报")
                return f"📅 {date_str} 每日想法汇总\n\n{feishu_content}"
    
    # 2. 从本地文件读取（备用方案）
    print("📊 从本地文件生成日报")
    
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
                    # 检查是否是今天的记录
                    if line.startswith("##") and date_str in line:
                        stats[category] += 1
                        # 读取下一行作为想法内容
                        if i + 1 < len(lines):
                            content = lines[i + 1].strip()
                            if content:
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


# ========== 修改后的周报函数 ==========
def generate_weekly_report(use_feishu=True):
    """生成周报
    
    Args:
        use_feishu: 是否优先从飞书读取
        
    Returns:
        str: 周报内容
    """
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    
    # 1. 尝试从飞书汇总文档读取本周数据
    if use_feishu and FEISHU_STORAGE_AVAILABLE and FEISHU_FOLDER_SUMMARY:
        token = get_feishu_tenant_access_token()
        if token:
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
    
    # 2. 从本地文件读取（备用方案）
    print("📊 从本地文件生成周报")
    
    stats = {cat: 0 for cat in CATEGORIES.keys()}
    category_ideas = {cat: [] for cat in CATEGORIES.keys()}
    
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
                    if line.startswith("##"):
                        for date_str in week_dates:
                            if date_str in line:
                                stats[category] += 1
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
            for idea in ideas[-5:]:  # 最多显示最近5条
                report += f"• {idea}\n"
    
    return report

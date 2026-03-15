#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书云文档存储模块 V2
功能：
- 在机器人空间自动创建文件夹
- 按日期创建文档
- 分类存储
- 每日汇总
"""

import os
import requests
from datetime import datetime

# 分类配置（与主程序保持一致）
CATEGORY_FOLDERS = {
    "work": {"name": "工作", "emoji": "💼"},
    "life": {"name": "生活", "emoji": "🏠"},
    "study": {"name": "学习", "emoji": "📚"},
    "inspiration": {"name": "灵感", "emoji": "💡"},
    "todo": {"name": "待办", "emoji": "✅"},
    "health": {"name": "健康", "emoji": "💪"},
    "finance": {"name": "财务", "emoji": "💰"},
    "other": {"name": "其他", "emoji": "📝"},
}

# 文件夹缓存
# 格式: {"work": "fldcnXXX", "life": "fldcnYYY", ...}
folder_cache = {}
summary_folder_id = None

# 文档缓存
# 格式: {folder_id: {date: doc_id}}
doc_cache = {}


def init_folders(token):
    """初始化文件夹结构
    
    在机器人空间创建：
    - 主文件夹：AI想法记录
    - 8个分类文件夹
    - 1个汇总文件夹
    
    Args:
        token: 飞书 access token
        
    Returns:
        bool: 是否成功
    """
    global folder_cache, summary_folder_id
    
    if not token:
        print("⚠️  未获取到 token，跳过文件夹初始化")
        return False
    
    print("🔄 开始初始化飞书文件夹...")
    
    try:
        # 1. 创建主文件夹 "AI想法记录"
        root_folder_id = create_folder(token, "AI想法记录", None)
        if not root_folder_id:
            print("❌ 创建主文件夹失败")
            return False
        
        print(f"✅ 主文件夹已创建: AI想法记录 ({root_folder_id})")
        
        # 2. 创建分类文件夹
        for category, info in CATEGORY_FOLDERS.items():
            folder_name = f"{info['emoji']} {info['name']}"
            folder_id = create_folder(token, folder_name, root_folder_id)
            
            if folder_id:
                folder_cache[category] = folder_id
                print(f"✅ 分类文件夹已创建: {folder_name} ({folder_id})")
            else:
                print(f"❌ 创建分类文件夹失败: {folder_name}")
        
        # 3. 创建汇总文件夹
        summary_folder_id = create_folder(token, "📊 每日汇总", root_folder_id)
        if summary_folder_id:
            print(f"✅ 汇总文件夹已创建: 📊 每日汇总 ({summary_folder_id})")
        else:
            print(f"❌ 创建汇总文件夹失败")
        
        print(f"🎉 文件夹初始化完成！共创建 {len(folder_cache)} 个分类文件夹")
        return True
        
    except Exception as e:
        print(f"❌ 文件夹初始化失败: {e}")
        return False


def create_folder(token, folder_name, parent_folder_id=None):
    """创建文件夹
    
    Args:
        token: 飞书 access token
        folder_name: 文件夹名称
        parent_folder_id: 父文件夹 ID（None 表示根目录）
        
    Returns:
        folder_id: 文件夹 ID，失败返回 None
    """
    try:
        url = "https://open.feishu.cn/open-apis/drive/v1/files/create_folder"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "name": folder_name
        }
        
        # 如果指定了父文件夹，添加到请求中
        if parent_folder_id:
            data["folder_token"] = parent_folder_id
        
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        
        if result.get("code") == 0:
            folder_id = result["data"]["token"]
            return folder_id
        else:
            print(f"❌ 创建文件夹失败: {result}")
            return None
            
    except Exception as e:
        print(f"❌ 创建文件夹异常: {e}")
        return None


def create_feishu_doc(token, folder_id, title):
    """在指定文件夹创建新文档
    
    Args:
        token: 飞书 access token
        folder_id: 文件夹 ID
        title: 文档标题
        
    Returns:
        doc_id: 文档 ID，失败返回 None
    """
    try:
        url = "https://open.feishu.cn/open-apis/docx/v1/documents"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "title": title
        }
        
        # 如果指定了文件夹，添加到请求中
        if folder_id:
            data["folder_token"] = folder_id
        
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        
        if result.get("code") == 0:
            doc_id = result["data"]["document"]["document_id"]
            print(f"✅ 创建文档成功: {title} ({doc_id})")
            return doc_id
        else:
            print(f"❌ 创建文档失败: {result}")
            return None
            
    except Exception as e:
        print(f"❌ 创建文档异常: {e}")
        return None


def get_or_create_daily_doc(token, category, date_str, category_name):
    """获取或创建今日文档
    
    Args:
        token: 飞书 access token
        category: 分类 ID
        date_str: 日期字符串，如 "2026-03-15"
        category_name: 分类名称，如 "工作"
        
    Returns:
        doc_id: 文档 ID
    """
    global folder_cache, doc_cache
    
    # 获取文件夹 ID
    folder_id = folder_cache.get(category)
    if not folder_id:
        print(f"⚠️  未找到分类文件夹: {category}")
        return None
    
    # 检查文档缓存
    if folder_id in doc_cache and date_str in doc_cache[folder_id]:
        return doc_cache[folder_id][date_str]
    
    # 文档标题
    title = f"{date_str} {category_name}记录"
    
    # 尝试查找已存在的文档
    doc_id = find_doc_by_title(token, folder_id, title)
    
    if doc_id:
        print(f"📄 找到已存在文档: {title}")
    else:
        # 创建新文档
        doc_id = create_feishu_doc(token, folder_id, title)
    
    # 缓存
    if doc_id:
        if folder_id not in doc_cache:
            doc_cache[folder_id] = {}
        doc_cache[folder_id][date_str] = doc_id
    
    return doc_id


def find_doc_by_title(token, folder_id, title):
    """在文件夹中查找指定标题的文档
    
    Args:
        token: 飞书 access token
        folder_id: 文件夹 ID
        title: 文档标题
        
    Returns:
        doc_id: 文档 ID，未找到返回 None
    """
    try:
        url = f"https://open.feishu.cn/open-apis/drive/v1/files"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        params = {
            "folder_token": folder_id,
            "page_size": 200
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result.get("code") == 0:
            files = result.get("data", {}).get("files", [])
            
            for file in files:
                if file.get("name") == title and file.get("type") == "docx":
                    doc_id = file.get("token")
                    return doc_id
        
        return None
        
    except Exception as e:
        print(f"⚠️  查找文档失败: {e}")
        return None


def append_to_doc(token, doc_id, content, timestamp):
    """追加内容到文档
    
    Args:
        token: 飞书 access token
        doc_id: 文档 ID
        content: 想法内容
        timestamp: 时间戳
        
    Returns:
        bool: 是否成功
    """
    try:
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/children"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 构造内容块
        data = {
            "children": [
                {
                    "block_type": 2,  # 标题3
                    "heading3": {
                        "elements": [{
                            "text_run": {
                                "text": timestamp
                            }
                        }]
                    }
                },
                {
                    "block_type": 1,  # 文本段落
                    "text": {
                        "elements": [{
                            "text_run": {
                                "text": content
                            }
                        }]
                    }
                },
                {
                    "block_type": 1,  # 空行
                    "text": {
                        "elements": [{
                            "text_run": {
                                "text": ""
                            }
                        }]
                    }
                }
            ],
            "index": -1  # 追加到文档末尾
        }
        
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        
        if result.get("code") == 0:
            return True
        else:
            print(f"❌ 追加内容失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 追加内容异常: {e}")
        return False


def save_to_feishu(token, category, content, timestamp, category_name):
    """保存想法到飞书文档
    
    同时保存到：
    1. 分类文件夹的今日文档
    2. 汇总文件夹的今日文档
    
    Args:
        token: 飞书 access token
        category: 分类 ID
        content: 想法内容
        timestamp: 完整时间戳
        category_name: 分类名称
        
    Returns:
        bool: 是否成功
    """
    global folder_cache, summary_folder_id
    
    if not token:
        return False
    
    # 如果文件夹未初始化，先初始化
    if not folder_cache:
        print("📁 文件夹未初始化，开始初始化...")
        if not init_folders(token):
            print("❌ 文件夹初始化失败，无法保存到飞书")
            return False
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = timestamp.split(" ")[1] if " " in timestamp else timestamp
    
    success = True
    
    # 1️⃣ 保存到分类文件夹
    doc_id = get_or_create_daily_doc(token, category, date_str, category_name)
    if doc_id:
        if append_to_doc(token, doc_id, content, time_str):
            print(f"✅ 已保存到分类文档: {category_name}")
        else:
            success = False
    else:
        print(f"❌ 无法创建分类文档: {category_name}")
        success = False
    
    # 2️⃣ 保存到汇总文件夹
    if summary_folder_id:
        summary_doc_id = get_or_create_daily_doc_summary(token, date_str)
        
        if summary_doc_id:
            summary_content = f"【{category_name}】{content}"
            if append_to_doc(token, summary_doc_id, summary_content, time_str):
                print(f"✅ 已保存到汇总文档")
            else:
                success = False
        else:
            print(f"❌ 无法创建汇总文档")
            success = False
    
    return success


def get_or_create_daily_doc_summary(token, date_str):
    """获取或创建今日汇总文档
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串
        
    Returns:
        doc_id: 文档 ID
    """
    global summary_folder_id, doc_cache
    
    if not summary_folder_id:
        return None
    
    # 检查缓存
    if summary_folder_id in doc_cache and date_str in doc_cache[summary_folder_id]:
        return doc_cache[summary_folder_id][date_str]
    
    title = f"{date_str} 全部想法记录"
    
    # 查找或创建
    doc_id = find_doc_by_title(token, summary_folder_id, title)
    
    if not doc_id:
        doc_id = create_feishu_doc(token, summary_folder_id, title)
    
    # 缓存
    if doc_id:
        if summary_folder_id not in doc_cache:
            doc_cache[summary_folder_id] = {}
        doc_cache[summary_folder_id][date_str] = doc_id
    
    return doc_id


def read_daily_summary(token, date_str):
    """读取指定日期的汇总文档
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串
        
    Returns:
        str: 文档内容，失败返回 None
    """
    global summary_folder_id
    
    if not summary_folder_id or not token:
        return None
    
    title = f"{date_str} 全部想法记录"
    doc_id = find_doc_by_title(token, summary_folder_id, title)
    
    if not doc_id:
        return None
    
    try:
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        result = response.json()
        
        if result.get("code") == 0:
            blocks = result.get("data", {}).get("blocks", [])
            
            content_parts = []
            for block in blocks:
                if block.get("block_type") == 1:
                    text_elements = block.get("text", {}).get("elements", [])
                    for elem in text_elements:
                        text = elem.get("text_run", {}).get("text", "")
                        if text:
                            content_parts.append(text)
            
            return "\n".join(content_parts)
        
        return None
        
    except Exception as e:
        print(f"❌ 读取文档失败: {e}")
        return None


# 测试和演示
if __name__ == "__main__":
    print("飞书云文档存储模块 V2")
    print("功能：在机器人空间自动创建文件夹")

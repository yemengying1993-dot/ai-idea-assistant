#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书云文档存储模块
功能：
- 在飞书云空间创建按日期命名的文档
- 分类存储到不同文件夹
- 每日汇总文档
- 支持日报/周报读取
"""

import os
import requests
from datetime import datetime, timedelta

# 文件夹 ID 配置
FEISHU_FOLDERS = {
    "work": os.getenv("FEISHU_FOLDER_WORK", ""),
    "life": os.getenv("FEISHU_FOLDER_LIFE", ""),
    "study": os.getenv("FEISHU_FOLDER_STUDY", ""),
    "inspiration": os.getenv("FEISHU_FOLDER_INSPIRATION", ""),
    "todo": os.getenv("FEISHU_FOLDER_TODO", ""),
    "health": os.getenv("FEISHU_FOLDER_HEALTH", ""),
    "finance": os.getenv("FEISHU_FOLDER_FINANCE", ""),
    "other": os.getenv("FEISHU_FOLDER_OTHER", ""),
}

FEISHU_FOLDER_SUMMARY = os.getenv("FEISHU_FOLDER_SUMMARY", "")

# 文档缓存（避免重复查询）
# 格式: {folder_id: {date: doc_id}}
doc_cache = {}


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
            "folder_token": folder_id,
            "title": title
        }
        
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


def get_or_create_daily_doc(token, folder_id, date_str, category_name):
    """获取或创建今日文档
    
    Args:
        token: 飞书 access token
        folder_id: 文件夹 ID
        date_str: 日期字符串，如 "2026-03-15"
        category_name: 分类名称，如 "工作"
        
    Returns:
        doc_id: 文档 ID
    """
    # 检查缓存
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
        # 获取文件夹下的文档列表
        url = f"https://open.feishu.cn/open-apis/drive/v1/files"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        params = {
            "folder_token": folder_id,
            "page_size": 200  # 最多查询200个文件
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result.get("code") == 0:
            files = result.get("data", {}).get("files", [])
            
            # 查找匹配的文档
            for file in files:
                if file.get("name") == title and file.get("type") == "docx":
                    doc_id = file.get("token")
                    print(f"📄 找到文档: {title} ({doc_id})")
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
            print(f"✅ 内容已追加到文档: {doc_id}")
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
        category: 分类 ID，如 "work"
        content: 想法内容
        timestamp: 完整时间戳，如 "2026-03-15 20:30:00"
        category_name: 分类名称，如 "工作"
        
    Returns:
        bool: 是否成功
    """
    if not token:
        print("⚠️  未获取到 token")
        return False
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = timestamp.split(" ")[1]  # 只取时间部分
    
    success = True
    
    # 1. 保存到分类文件夹
    folder_id = FEISHU_FOLDERS.get(category)
    if folder_id:
        doc_id = get_or_create_daily_doc(token, folder_id, date_str, category_name)
        if doc_id:
            if append_to_doc(token, doc_id, content, time_str):
                print(f"✅ 已保存到分类文档: {category_name}")
            else:
                success = False
        else:
            print(f"❌ 无法创建分类文档: {category_name}")
            success = False
    else:
        print(f"⚠️  未配置文件夹 ID: {category}")
        success = False
    
    # 2. 保存到汇总文件夹
    if FEISHU_FOLDER_SUMMARY:
        summary_doc_id = get_or_create_daily_doc(
            token, 
            FEISHU_FOLDER_SUMMARY, 
            date_str, 
            "全部想法"
        )
        
        if summary_doc_id:
            # 汇总文档格式：分类 + 时间 + 内容
            summary_content = f"【{category_name}】{content}"
            if append_to_doc(token, summary_doc_id, summary_content, time_str):
                print(f"✅ 已保存到汇总文档")
            else:
                success = False
        else:
            print(f"❌ 无法创建汇总文档")
            success = False
    else:
        print(f"⚠️  未配置汇总文件夹 ID")
    
    return success


def read_daily_summary(token, date_str):
    """读取指定日期的汇总文档
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串，如 "2026-03-15"
        
    Returns:
        str: 文档内容，失败返回 None
    """
    if not FEISHU_FOLDER_SUMMARY or not token:
        return None
    
    title = f"{date_str} 全部想法记录"
    doc_id = find_doc_by_title(token, FEISHU_FOLDER_SUMMARY, title)
    
    if not doc_id:
        return None
    
    try:
        # 获取文档内容
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        result = response.json()
        
        if result.get("code") == 0:
            blocks = result.get("data", {}).get("blocks", [])
            
            # 提取文本内容
            content_parts = []
            for block in blocks:
                if block.get("block_type") == 1:  # 文本段落
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


# 测试函数
if __name__ == "__main__":
    print("飞书云文档存储模块")
    print("请在主程序中导入使用")

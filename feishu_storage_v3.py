#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书云文档存储模块 V3 - 简化版
功能：
- 直接在机器人空间创建文档（不使用文件夹）
- 通过文档标题区分分类
- 按日期创建文档
"""

import os
import requests
from datetime import datetime

# 文档缓存
# 格式: {category: {date: doc_id}}
doc_cache = {}
summary_doc_cache = {}


def create_feishu_doc(token, title):
    """创建新文档（在机器人根目录）
    
    Args:
        token: 飞书 access token
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
            # 不传 folder_token，文档创建在机器人根目录
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


def find_doc_by_title(token, title):
    """查找指定标题的文档
    
    Args:
        token: 飞书 access token
        title: 文档标题
        
    Returns:
        doc_id: 文档 ID，未找到返回 None
    """
    try:
        # 使用搜索 API 查找文档
        url = "https://open.feishu.cn/open-apis/drive/v1/files"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 不指定 folder_token，搜索所有文档
        params = {
            "page_size": 200
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result.get("code") == 0:
            files = result.get("data", {}).get("files", [])
            
            # 查找匹配的文档
            for file in files:
                if file.get("name") == title and file.get("type") == "docx":
                    doc_id = file.get("token")
                    print(f"📄 找到已存在文档: {title} ({doc_id})")
                    return doc_id
        
        return None
        
    except Exception as e:
        print(f"⚠️  查找文档失败: {e}")
        return None


def get_or_create_daily_doc(token, category, date_str, category_name, emoji):
    """获取或创建今日文档
    
    Args:
        token: 飞书 access token
        category: 分类 ID
        date_str: 日期字符串
        category_name: 分类名称
        emoji: 分类图标
        
    Returns:
        doc_id: 文档 ID
    """
    global doc_cache
    
    # 检查缓存
    if category in doc_cache and date_str in doc_cache[category]:
        return doc_cache[category][date_str]
    
    # 文档标题（包含 emoji 和分类）
    title = f"{date_str} {emoji} {category_name}记录"
    
    # 查找已存在的文档
    doc_id = find_doc_by_title(token, title)
    
    if not doc_id:
        # 创建新文档
        doc_id = create_feishu_doc(token, title)
    
    # 缓存
    if doc_id:
        if category not in doc_cache:
            doc_cache[category] = {}
        doc_cache[category][date_str] = doc_id
    
    return doc_id


def get_or_create_summary_doc(token, date_str):
    """获取或创建今日汇总文档
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串
        
    Returns:
        doc_id: 文档 ID
    """
    global summary_doc_cache
    
    # 检查缓存
    if date_str in summary_doc_cache:
        return summary_doc_cache[date_str]
    
    # 文档标题
    title = f"{date_str} 📊 全部想法汇总"
    
    # 查找已存在的文档
    doc_id = find_doc_by_title(token, title)
    
    if not doc_id:
        # 创建新文档
        doc_id = create_feishu_doc(token, title)
    
    # 缓存
    if doc_id:
        summary_doc_cache[date_str] = doc_id
    
    return doc_id


def get_doc_root_block(token, doc_id):
    """获取文档的根块 ID
    
    Args:
        token: 飞书 access token
        doc_id: 文档 ID
        
    Returns:
        block_id: 根块 ID
    """
    try:
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        params = {
            "page_size": 1
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result.get("code") == 0:
            # 获取第一个块（根块）
            items = result.get("data", {}).get("items", [])
            if items and len(items) > 0:
                block_id = items[0].get("block_id")
                if block_id:
                    print(f"✅ 获取到文档根块 ID: {block_id}")
                    return block_id
        
        print(f"⚠️  无法获取文档根块: {result}")
        return None
        
    except Exception as e:
        print(f"❌ 获取文档根块失败: {e}")
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
        # 先获取文档的根块 ID
        root_block_id = get_doc_root_block(token, doc_id)
        if not root_block_id:
            print("❌ 无法获取文档根块 ID")
            return False
        
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{root_block_id}/children"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 最简化版本（block_type: 2 = 文本块）
        data = {
            "children": [
                {
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": f"### {timestamp}\n{content}\n\n"
                                }
                            }
                        ],
                        "style": {}
                    }
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        # 详细的响应日志
        print(f"📊 追加内容 API 响应状态: {response.status_code}")
        
        # 检查响应状态
        if response.status_code != 200:
            print(f"❌ HTTP 错误: {response.status_code}")
            print(f"   完整响应: {response.text}")
            return False
        
        # 尝试解析 JSON
        try:
            result = response.json()
        except Exception as json_err:
            print(f"❌ JSON 解析失败: {json_err}")
            print(f"   响应文本: {response.text[:500]}")
            return False
        
        # 检查业务逻辑错误
        if result.get("code") == 0:
            print(f"✅ 内容追加成功")
            return True
        else:
            print(f"❌ 追加内容失败: {result}")
            return False
            
    except requests.exceptions.RequestException as req_err:
        print(f"❌ 网络请求异常: {req_err}")
        return False
    except Exception as e:
        print(f"❌ 追加内容异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def save_to_feishu(token, category, content, timestamp, category_name, category_emoji):
    """保存想法到飞书文档
    
    同时保存到：
    1. 分类文档
    2. 汇总文档
    
    Args:
        token: 飞书 access token
        category: 分类 ID
        content: 想法内容
        timestamp: 完整时间戳
        category_name: 分类名称
        category_emoji: 分类图标
        
    Returns:
        bool: 是否成功
    """
    if not token:
        print("⚠️  未获取到 token")
        return False
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = timestamp.split(" ")[1] if " " in timestamp else timestamp
    
    success = True
    
    # 1️⃣ 保存到分类文档
    doc_id = get_or_create_daily_doc(token, category, date_str, category_name, category_emoji)
    if doc_id:
        if append_to_doc(token, doc_id, content, time_str):
            print(f"✅ 已保存到分类文档: {category_name}")
        else:
            success = False
    else:
        print(f"❌ 无法创建分类文档: {category_name}")
        success = False
    
    # 2️⃣ 保存到汇总文档
    summary_doc_id = get_or_create_summary_doc(token, date_str)
    if summary_doc_id:
        summary_content = f"【{category_emoji} {category_name}】{content}"
        if append_to_doc(token, summary_doc_id, summary_content, time_str):
            print(f"✅ 已保存到汇总文档")
        else:
            success = False
    else:
        print(f"❌ 无法创建汇总文档")
        success = False
    
    return success


def read_daily_summary(token, date_str):
    """读取指定日期的汇总文档
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串
        
    Returns:
        str: 文档内容，失败返回 None
    """
    if not token:
        return None
    
    title = f"{date_str} 📊 全部想法汇总"
    doc_id = find_doc_by_title(token, title)
    
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


# 测试
if __name__ == "__main__":
    print("飞书云文档存储模块 V3 - 简化版")
    print("不使用文件夹，直接创建文档")

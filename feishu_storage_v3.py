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
import json
import requests
from datetime import datetime
from pytz import timezone

# 时区配置
TIMEZONE = os.getenv("TIMEZONE", "Asia/Shanghai")
tz = timezone(TIMEZONE)

# 分类配置
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
        dict: {"doc_id": str, "file_token": str} 或 None
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
            doc_data = result["data"]["document"]
            doc_id = doc_data.get("document_id")

            # 尝试获取 file_token（可能在响应中）
            file_token = doc_data.get("file_token") or doc_data.get("token")

            print(f"✅ 创建文档成功: {title}")
            
            return {
                "doc_id": doc_id,
                "file_token": file_token
            }
        else:
            print(f"❌ 创建文档失败: {result}")
            return None
            
    except Exception as e:
        print(f"❌ 创建文档异常: {e}")
        import traceback
        traceback.print_exc()
        return None


def add_doc_permission(token, doc_id, user_open_id):
    """给文档添加协作者（可编辑权限）
    
    Args:
        token: 飞书 access token
        doc_id: 文档 ID
        user_open_id: 用户的 open_id
        
    Returns:
        bool: 是否成功
    """
    try:
        # URL查询参数：文档类型
        url = f"https://open.feishu.cn/open-apis/drive/v1/permissions/{doc_id}/members?type=docx"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 请求体参数：协作者信息
        data = {
            "member_type": "openid",
            "member_id": user_open_id,
            "perm": "edit",  # 可编辑权限
            "type": "user"   # 协作者类型：用户
        }
        
        response = requests.post(url, headers=headers, json=data)
        result = response.json()

        if result.get("code") == 0:
            print(f"✅ 已授予编辑权限: {doc_id} → {user_open_id}")
            return True
        else:
            # 可能已经有权限了，不算错误
            if result.get("code") == 1063003:  # Invalid operation - 可能权限已存在
                print(f"ℹ️  用户已有权限或权限更高: {doc_id}")
                return True
            print(f"⚠️  授权失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 授权异常: {e}")
        import traceback
        traceback.print_exc()
        return False


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


def get_or_create_unified_daily_doc(token, date_str, user_open_id=None):
    """获取或创建统一的每日文档（自动授予用户编辑权限）
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串
        user_open_id: 用户的 open_id（可选，用于自动授权）
        
    Returns:
        doc_id: 文档 ID
    """
    global doc_cache
    
    # 检查缓存（使用特殊key "unified"）
    if "unified" in doc_cache and date_str in doc_cache["unified"]:
        return doc_cache["unified"][date_str]
    
    # 文档标题：每日记录
    title = f"{date_str} 📝 每日记录"
    
    # 查找已存在的文档
    doc_id = find_doc_by_title(token, title)
    
    is_new_doc = False
    if not doc_id:
        # 创建新文档
        result = create_feishu_doc(token, title)
        if result:
            doc_id = result.get("doc_id")
            is_new_doc = True
    
    # 如果是新文档且有 user_open_id，自动授予编辑权限
    if is_new_doc and doc_id and user_open_id:
        print(f"🔍 尝试授权每日文档: doc_id={doc_id}")
        add_doc_permission(token, doc_id, user_open_id)
    
    # 缓存 doc_id
    if doc_id:
        if "unified" not in doc_cache:
            doc_cache["unified"] = {}
        doc_cache["unified"][date_str] = doc_id
    
    return doc_id


# 汇总文档函数已废弃，现在使用统一的每日文档


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


def insert_image_to_doc(token, doc_id, root_block_id, message_id, image_key):
    """将飞书 IM 图片插入文档，按官方三步流程：
    1. 创建空图片块，获取 block_id
    2. 用 block_id 作为 parent_node 上传图片素材，获取 file_token
    3. 用 replace_image 操作将 file_token 关联到图片块

    Args:
        token: 飞书 access token
        doc_id: 文档 ID
        root_block_id: 父块 ID（文档根块）
        message_id: 飞书消息 ID
        image_key: 消息中的图片 key

    Returns:
        bool
    """
    headers_json = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        # 步骤一：创建空图片块
        create_url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{root_block_id}/children"
        create_resp = requests.post(
            create_url,
            headers=headers_json,
            json={"children": [{"block_type": 27, "image": {}}]},
        )
        create_result = create_resp.json()
        if create_result.get("code") != 0:
            print(f"❌ 创建图片块失败: {create_result}")
            return False
        block_id = create_result["data"]["children"][0]["block_id"]
        print(f"✅ 图片块创建成功: {block_id}")

        # 步骤二：从 IM 下载图片
        download_url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{image_key}"
        img_response = requests.get(download_url, headers=headers_auth, params={"type": "image"})
        if img_response.status_code != 200:
            print(f"❌ 下载图片失败: HTTP {img_response.status_code}")
            return False

        content_type = img_response.headers.get("Content-Type", "image/png")
        ext = "jpg" if "jpeg" in content_type or "jpg" in content_type else \
              "gif" if "gif" in content_type else \
              "webp" if "webp" in content_type else "png"
        image_data = img_response.content

        # 步骤二：上传图片素材，parent_node 为图片块的 block_id
        upload_resp = requests.post(
            "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all",
            headers=headers_auth,
            data={
                "file_name": f"{image_key}.{ext}",
                "parent_type": "docx_image",
                "parent_node": block_id,
                "size": str(len(image_data)),
            },
            files={"file": (f"{image_key}.{ext}", image_data, content_type)},
        )
        upload_result = upload_resp.json()
        if upload_result.get("code") != 0:
            print(f"❌ 图片上传失败: {upload_result}")
            return False
        file_token = upload_result["data"]["file_token"]
        print(f"✅ 图片上传成功: {file_token}")

        # 步骤三：关联 file_token 到图片块
        update_url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{block_id}"
        update_resp = requests.patch(
            update_url,
            headers=headers_json,
            json={"replace_image": {"token": file_token}},
        )
        update_result = update_resp.json()
        if update_result.get("code") != 0:
            print(f"❌ 关联图片失败: {update_result}")
            return False
        print(f"✅ 图片关联成功")
        return True

    except Exception as e:
        print(f"❌ 图片插入异常: {e}")
        import traceback
        traceback.print_exc()
        return False
        return False


def append_to_doc(token, doc_id, content, timestamp, category_emoji="", category_name="",
                  image_keys=None, message_id=None):
    """追加内容到文档（带分类标题，支持图片）

    Args:
        token: 飞书 access token
        doc_id: 文档 ID
        content: 想法内容
        timestamp: 时间戳
        category_emoji: 分类图标（可选）
        category_name: 分类名称（可选）
        image_keys: 图片 key 列表（可选）
        message_id: 消息 ID，下载图片时需要（可选）

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
        
        # 格式化内容：包含分类标题
        if category_emoji and category_name:
            formatted_content = f"## {category_emoji} {category_name}\n**{timestamp}**\n{content}\n\n"
        else:
            formatted_content = f"**{timestamp}**\n{content}\n\n"
        
        # 最简化版本（block_type: 2 = 文本块）
        data = {
            "children": [
                {
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {
                                "text_run": {
                                    "content": formatted_content
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
            return False
        
        # 尝试解析 JSON
        try:
            result = response.json()
        except Exception as json_err:
            print(f"❌ JSON 解析失败: {json_err}")
            return False
        
        # 检查业务逻辑错误
        if result.get("code") == 0:
            print(f"✅ 内容追加成功")
        else:
            print(f"❌ 追加内容失败: {result}")
            return False

        # 插入图片块
        if image_keys and message_id:
            for image_key in image_keys:
                insert_image_to_doc(token, doc_id, root_block_id, message_id, image_key)

        return True

    except requests.exceptions.RequestException as req_err:
        print(f"❌ 网络请求异常: {req_err}")
        return False
    except Exception as e:
        print(f"❌ 追加内容异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def save_to_feishu(token, category, content, timestamp, category_name, category_emoji,
                   user_open_id=None, image_keys=None, message_id=None):
    """保存想法到飞书文档（自动授予用户编辑权限）
    
    保存到统一的每日文档，内容按分类分段
    
    Args:
        token: 飞书 access token
        category: 分类 ID
        content: 想法内容
        timestamp: 完整时间戳
        category_name: 分类名称
        category_emoji: 分类图标
        user_open_id: 用户的 open_id（可选，用于自动授权编辑权限）
        
    Returns:
        dict: {"success": bool, "doc_url": str}
    """
    if not token:
        print("⚠️  未获取到 token")
        return {"success": False, "doc_url": None}
    
    # 使用配置的时区获取当前日期
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = timestamp.split(" ")[1] if " " in timestamp else timestamp
    
    # 获取或创建统一的每日文档
    doc_id = get_or_create_unified_daily_doc(token, date_str, user_open_id)
    
    if not doc_id:
        print(f"❌ 无法创建每日文档")
        return {"success": False, "doc_url": None}
    
    # 追加内容（带分类标题）
    if append_to_doc(token, doc_id, content, time_str, category_emoji, category_name,
                     image_keys=image_keys, message_id=message_id):
        print(f"✅ 已保存到每日文档: {category_emoji} {category_name}")
        doc_url = f"https://feishu.cn/docx/{doc_id}"
        return {
            "success": True,
            "doc_url": doc_url
        }
    else:
        print(f"❌ 保存失败")
        return {"success": False, "doc_url": None}


def read_daily_summary(token, date_str):
    """读取指定日期的每日文档
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串
        
    Returns:
        str: 文档内容，失败返回 None
    """
    if not token:
        return None
    
    # 统一文档标题
    title = f"{date_str} 📝 每日记录"
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
            blocks = result.get("data", {}).get("items", [])
            
            content_parts = []
            for block in blocks:
                if block.get("block_type") == 2:  # 文本块
                    text_elements = block.get("text", {}).get("elements", [])
                    for elem in text_elements:
                        text = elem.get("text_run", {}).get("content", "")
                        if text:
                            content_parts.append(text)
            
            return "\n".join(content_parts)
        
        return None
        
    except Exception as e:
        print(f"❌ 读取文档失败: {e}")
        return None


def list_all_docs(token):
    """列出所有历史文档（按日期分组）
    
    Args:
        token: 飞书 access token
        
    Returns:
        dict: {date_str: [{'title': str, 'url': str, 'emoji': str, 'category': str}]}
    """
    if not token:
        return {}
    
    try:
        url = "https://open.feishu.cn/open-apis/drive/v1/files"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 搜索所有文档
        params = {
            "page_size": 200  # 一次最多200个
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result.get("code") != 0:
            print(f"❌ 获取文档列表失败: {result}")
            return {}
        
        files = result.get("data", {}).get("files", [])
        
        # 按日期分组
        docs_by_date = {}
        
        for file in files:
            if file.get("type") != "docx":
                continue
            
            title = file.get("name", "")
            doc_id = file.get("token", "")
            
            # 检查是否是我们的文档（格式：2026-03-16 emoji 分类记录）
            if not doc_id or len(title) < 10:
                continue
            
            # 提取日期（前10个字符应该是 YYYY-MM-DD）
            date_str = title[:10]
            
            # 验证日期格式
            try:
                from datetime import datetime
                datetime.strptime(date_str, "%Y-%m-%d")
            except:
                continue  # 不是我们的文档格式
            
            # 提取分类信息
            if "📊" in title and "汇总" in title:
                emoji = "📊"
                category = "汇总"
            elif "💼" in title and "工作" in title:
                emoji = "💼"
                category = "工作"
            elif "🏠" in title and "生活" in title:
                emoji = "🏠"
                category = "生活"
            elif "📚" in title and "学习" in title:
                emoji = "📚"
                category = "学习"
            elif "💡" in title and "灵感" in title:
                emoji = "💡"
                category = "灵感"
            elif "✅" in title and "待办" in title:
                emoji = "✅"
                category = "待办"
            elif "💪" in title and "健康" in title:
                emoji = "💪"
                category = "健康"
            elif "💰" in title and "财务" in title:
                emoji = "💰"
                category = "财务"
            elif "📝" in title and "其他" in title:
                emoji = "📝"
                category = "其他"
            else:
                continue  # 不是我们的文档
            
            # 添加到分组
            if date_str not in docs_by_date:
                docs_by_date[date_str] = []
            
            docs_by_date[date_str].append({
                'title': title,
                'url': f"https://feishu.cn/docx/{doc_id}",
                'emoji': emoji,
                'category': category
            })
        
        # 对每个日期的文档排序（汇总在前）
        for date_str in docs_by_date:
            docs_by_date[date_str].sort(key=lambda x: (0 if x['category'] == '汇总' else 1, x['category']))
        
        return docs_by_date
        
    except Exception as e:
        print(f"❌ 列出所有文档失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


def list_today_docs(token):
    """列出今日所有文档
    
    Args:
        token: 飞书 access token
        
    Returns:
        list: [{'title': str, 'url': str, 'emoji': str, 'category': str}]
    """
    if not token:
        return []
    
    # 获取今日日期
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    
    return list_docs_by_date(token, date_str)


def list_docs_by_date(token, date_str):
    """列出指定日期的文档（现在每天只有一个统一文档）
    
    Args:
        token: 飞书 access token
        date_str: 日期字符串 (YYYY-MM-DD)
        
    Returns:
        list: [{'title': str, 'url': str, 'emoji': str, 'category': str}]
    """
    if not token:
        return []
    
    docs = []
    
    # 查找统一的每日文档
    title = f"{date_str} 📝 每日记录"
    doc_id = find_doc_by_title(token, title)
    if doc_id:
        docs.append({
            'title': title,
            'url': f"https://feishu.cn/docx/{doc_id}",
            'emoji': '📝',
            'category': '每日记录'
        })
    
    return docs

# 测试
if __name__ == "__main__":
    print("飞书云文档存储模块 V3 - 简化版")
    print("每天一个统一文档，按分类分段")

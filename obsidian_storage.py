#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obsidian Vault 存储模块（GitHub API 版）
- 通过 GitHub REST API 直接读写文件，无需 git 命令
- 每日一个笔记，YAML frontmatter + 分类标签
"""

import os
import base64
import requests
from datetime import datetime

# ========== 配置 ==========
OBSIDIAN_GITHUB_TOKEN = os.getenv("OBSIDIAN_GITHUB_TOKEN", "")
OBSIDIAN_GITHUB_REPO = os.getenv("OBSIDIAN_GITHUB_REPO", "")   # e.g. luckylucky-ai/obsidian
OBSIDIAN_NOTES_SUBDIR = os.getenv("OBSIDIAN_NOTES_SUBDIR", "Ideas")
GITHUB_API = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"token {OBSIDIAN_GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def _file_path(date_str):
    """仓库内的文件路径"""
    return f"{OBSIDIAN_NOTES_SUBDIR}/{date_str}.md"


def _get_file(path):
    """获取文件内容和 SHA，文件不存在返回 (None, None)"""
    url = f"{GITHUB_API}/repos/{OBSIDIAN_GITHUB_REPO}/contents/{path}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def _put_file(path, content, sha, commit_msg):
    """创建或更新文件"""
    url = f"{GITHUB_API}/repos/{OBSIDIAN_GITHUB_REPO}/contents/{path}"
    body = {
        "message": commit_msg,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        body["sha"] = sha
    resp = requests.put(url, headers=_headers(), json=body, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _build_daily_note(date_str):
    """生成新的每日笔记初始内容"""
    return f"""---
date: {date_str}
type: daily-ideas
tags:
  - ideas
---

# {date_str} 每日想法

"""


def save_to_obsidian(category, content, timestamp, category_name, category_emoji,
                     image_keys=None, **kwargs):
    """保存想法到 Obsidian vault（通过 GitHub API）

    Returns:
        dict: {{"success": bool}}
    """
    if not OBSIDIAN_GITHUB_TOKEN or not OBSIDIAN_GITHUB_REPO:
        print("⚠️  OBSIDIAN_GITHUB_TOKEN 或 OBSIDIAN_GITHUB_REPO 未配置")
        return {"success": False}

    try:
        date_str = timestamp.split(" ")[0] if " " in timestamp else timestamp
        time_str = timestamp.split(" ")[1] if " " in timestamp else ""
        path = _file_path(date_str)

        # 读取已有文件（或创建新文件）
        existing, sha = _get_file(path)
        note = existing if existing else _build_daily_note(date_str)

        # 追加新条目
        entry = f"## {category_emoji} {category_name} - {time_str}\n\n{content}\n"
        if image_keys:
            for key in image_keys:
                entry += f"\n> 📷 图片: `{key}`\n"
        entry += "\n---\n\n"

        note += entry

        # 追加分类 tag 到 frontmatter
        tag = f"  - ideas/{category}"
        if tag not in note:
            note = note.replace("  - ideas\n", f"  - ideas\n{tag}\n", 1)

        # 写回 GitHub
        commit_msg = f"auto: add {category_name} idea ({date_str} {time_str})"
        _put_file(path, note, sha, commit_msg)

        print(f"✅ Obsidian 笔记已同步: {OBSIDIAN_GITHUB_REPO}/{path}")
        return {"success": True}

    except Exception as e:
        print(f"❌ Obsidian 保存失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False}


def read_daily_notes(date_str):
    """读取指定日期的 Obsidian 笔记

    Returns:
        str: 笔记内容，不存在返回空字符串
    """
    if not OBSIDIAN_GITHUB_TOKEN or not OBSIDIAN_GITHUB_REPO:
        return ""
    try:
        content, _ = _get_file(_file_path(date_str))
        return content or ""
    except Exception:
        return ""

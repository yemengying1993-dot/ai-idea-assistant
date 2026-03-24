#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obsidian Vault 存储模块
- 将想法保存为 Obsidian 兼容的 Markdown 文件（每日一个笔记）
- 通过 Git 仓库同步，配合 Obsidian Git 插件使用
"""

import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime


# ========== 配置 ==========
OBSIDIAN_REPO_URL = os.getenv("OBSIDIAN_REPO_URL", "")  # Git 仓库地址
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "obsidian_vault")  # 本地克隆路径
OBSIDIAN_NOTES_SUBDIR = os.getenv("OBSIDIAN_NOTES_SUBDIR", "Ideas")  # vault 内的笔记子目录

_vault_initialized = False


def _run_git(args, cwd):
    """执行 git 命令"""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"⚠️  git {' '.join(args)} 失败: {result.stderr.strip()}")
    return result


def init_vault():
    """初始化 Obsidian vault（克隆或拉取最新）"""
    global _vault_initialized

    vault = Path(OBSIDIAN_VAULT_PATH)

    if not OBSIDIAN_REPO_URL:
        print("⚠️  OBSIDIAN_REPO_URL 未配置，Obsidian 存储不可用")
        return False

    try:
        if not vault.exists():
            print(f"📥 克隆 Obsidian vault: {OBSIDIAN_REPO_URL}")
            result = subprocess.run(
                ["git", "clone", OBSIDIAN_REPO_URL, str(vault)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                print(f"❌ 克隆失败: {result.stderr.strip()}")
                return False
        else:
            # 已存在，拉取最新
            _run_git(["pull", "--rebase"], cwd=str(vault))

        # 确保笔记子目录存在
        notes_dir = vault / OBSIDIAN_NOTES_SUBDIR
        notes_dir.mkdir(parents=True, exist_ok=True)

        _vault_initialized = True
        print(f"✅ Obsidian vault 就绪: {vault}")
        return True

    except Exception as e:
        print(f"❌ Obsidian vault 初始化失败: {e}")
        return False


def _git_sync(vault_path):
    """提交并推送变更"""
    try:
        _run_git(["add", "-A"], cwd=vault_path)

        # 检查是否有变更需要提交
        status = _run_git(["status", "--porcelain"], cwd=vault_path)
        if not status.stdout.strip():
            return True  # 没有变更，跳过

        _run_git(
            ["commit", "-m", f"auto: update ideas {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            cwd=vault_path,
        )

        result = _run_git(["push"], cwd=vault_path)
        if result.returncode == 0:
            print("✅ Obsidian vault 已同步到远程仓库")
            return True
        else:
            print(f"⚠️  推送失败，变更已本地保存: {result.stderr.strip()}")
            return True  # 本地已保存，推送失败不算完全失败

    except Exception as e:
        print(f"⚠️  Git 同步异常: {e}")
        return False


def _get_daily_note_path(date_str):
    """获取每日笔记的文件路径"""
    vault = Path(OBSIDIAN_VAULT_PATH)
    notes_dir = vault / OBSIDIAN_NOTES_SUBDIR
    return notes_dir / f"{date_str}.md"


def _build_frontmatter(date_str, tags):
    """构建 YAML frontmatter"""
    tag_str = "\n".join(f"  - {t}" for t in tags)
    return f"""---
date: {date_str}
type: daily-ideas
tags:
{tag_str}
---
"""


def save_to_obsidian(category, content, timestamp, category_name, category_emoji,
                     image_keys=None, **kwargs):
    """保存想法到 Obsidian vault

    Args:
        category: 分类 ID（如 work, life）
        content: 想法内容
        timestamp: 时间戳字符串
        category_name: 分类中文名
        category_emoji: 分类 emoji
        image_keys: 图片 key 列表（暂存为占位符）

    Returns:
        dict: {"success": bool}
    """
    global _vault_initialized

    if not _vault_initialized:
        if not init_vault():
            return {"success": False}

    try:
        date_str = timestamp.split(" ")[0] if " " in timestamp else timestamp
        time_str = timestamp.split(" ")[1] if " " in timestamp else ""
        note_path = _get_daily_note_path(date_str)

        # 如果文件不存在，创建并写入 frontmatter 和标题
        if not note_path.exists():
            frontmatter = _build_frontmatter(date_str, ["ideas"])
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(frontmatter)
                f.write(f"\n# {date_str} 每日想法\n\n")

        # 追加想法条目
        entry = f"## {category_emoji} {category_name} - {time_str}\n\n{content}\n"

        # 图片占位（Obsidian 本地无法直接获取飞书图片，记录 image_key 供参考）
        if image_keys:
            for key in image_keys:
                entry += f"\n> 📷 图片: `{key}`\n"

        entry += "\n---\n\n"

        with open(note_path, "a", encoding="utf-8") as f:
            f.write(entry)

        print(f"✅ Obsidian 笔记已保存: {note_path}")

        # 读取现有 frontmatter，追加新 tag
        _update_frontmatter_tags(note_path, category)

        # Git 同步
        _git_sync(str(Path(OBSIDIAN_VAULT_PATH)))

        return {"success": True}

    except Exception as e:
        print(f"❌ Obsidian 保存失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False}


def _update_frontmatter_tags(note_path, category):
    """在 frontmatter 中追加分类 tag（去重）"""
    try:
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.startswith("---"):
            return

        end_idx = content.index("---", 3)
        frontmatter = content[3:end_idx]
        body = content[end_idx + 3:]

        tag = f"ideas/{category}"
        if tag not in frontmatter:
            # 在 tags 列表末尾追加
            frontmatter = frontmatter.rstrip("\n") + f"\n  - {tag}\n"

        new_content = f"---{frontmatter}---{body}"
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(new_content)

    except Exception:
        pass  # frontmatter 更新失败不影响主流程


def read_daily_notes(date_str):
    """读取指定日期的 Obsidian 笔记内容

    Returns:
        str: 笔记内容，不存在则返回空字符串
    """
    note_path = _get_daily_note_path(date_str)
    if note_path.exists():
        with open(note_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

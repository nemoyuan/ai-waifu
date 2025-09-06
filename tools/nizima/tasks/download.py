"""
下载任务实现

负责从网络下载文件到本地
"""

import asyncio
from pathlib import Path
from typing import Any, Optional

import aiohttp

from .base import is_shutdown_requested, Task


class DownloadTask(Task):
    """下载任务

    从指定URL下载文件到本地路径
    """

    def __init__(
        self,
        task_id: str,
        url: str,
        target_path: Path,
        deps_on: list = None,
        max_retries: int = 3,
        file_name: Optional[str] = None,
        is_export: bool = False,
    ):
        """初始化下载任务

        Args:
            task_id: 任务ID
            url: 下载URL
            target_path: 目标文件路径
            deps_on: 依赖的任务ID列表
            max_retries: 最大重试次数
            file_name: 文件名（用于export下载）
            is_export: 是否为export下载（需要POST请求）
        """
        super().__init__(task_id, deps_on)
        self.url = url
        self.target_path = Path(target_path)
        self.max_retries = max_retries
        self.file_name = file_name
        self.is_export = is_export

    def is_completed(self) -> bool:
        """检查文件是否已下载"""
        return self.target_path.exists()

    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    async def execute(self) -> Path:
        """执行下载"""
        # 检查是否请求关闭
        if is_shutdown_requested():
            raise Exception("用户请求中断下载")

        # 确保目标目录存在
        self.target_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"⬇️ 下载: {self.url}")

        last_error = None

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),
            connector=aiohttp.TCPConnector(limit=20),
        ) as session:

            for attempt in range(self.max_retries + 1):
                try:
                    if self.is_export:
                        # export文件需要特殊的POST请求
                        form_data = aiohttp.FormData()
                        form_data.add_field("fileName", self.file_name or "export.zip")

                        async with session.post(self.url, data=form_data) as response:
                            # 检查是否返回了登录页面
                            content_type = response.headers.get("content-type", "")
                            if "text/html" in content_type:
                                raise Exception(
                                    "Export下载需要用户登录认证。请在浏览器中登录Nizima账户后再尝试，或者仅使用Preview模式。"
                                )

                            response.raise_for_status()
                            result = await response.json()

                            if not result.get("isSucceeded") or not result.get(
                                "downloadUrl"
                            ):
                                raise Exception(f"下载API返回失败: {result}")

                            # 使用返回的downloadUrl下载文件
                            async with session.get(
                                result["downloadUrl"]
                            ) as file_response:
                                file_response.raise_for_status()
                                content = await file_response.read()
                    else:
                        # 普通GET请求
                        async with session.get(self.url) as response:
                            response.raise_for_status()
                            content = await response.read()

                    # 写入文件
                    with open(self.target_path, "wb") as f:
                        f.write(content)

                    print(
                        f"✅ 下载完成: {self.target_path.name} ({self._format_file_size(len(content))})"
                    )

                    self.mark_completed(self.target_path)
                    return self.target_path

                except Exception as e:
                    last_error = e

                    if attempt < self.max_retries:
                        # 指数退避：3秒、6秒、12秒
                        delay = 3 * (2**attempt)
                        print(
                            f"⚠️ 下载失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}"
                        )
                        print(f"🔄 {delay}秒后重试...")
                        await asyncio.sleep(delay)
                    else:
                        print(f"❌ 下载最终失败 {self.url}: {e}")

        # 如果到这里说明所有重试都失败了
        self.mark_failed(str(last_error))
        raise Exception(f"下载失败: {last_error}")

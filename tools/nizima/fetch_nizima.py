#!/usr/bin/env python3
"""
Nizima Live2D模型下载器 v3.0
支持同时下载preview和export版本
"""

import asyncio
import json
import os
import shutil
import signal
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp


# ==================== 数据结构 ====================
# Export功能需要用户登录认证，目前仅支持preview下载
ENABLE_EXPORT_ATTEMPT = False

# 脚本版本控制
SCRIPT_VERSION = "v4"

# 全局中断标志
_shutdown_requested = False


def signal_handler(signum, frame):
    """信号处理器：优雅处理中断"""
    global _shutdown_requested
    _shutdown_requested = True
    print("\n🛑 收到中断信号，正在安全停止...")
    print("⏳ 等待当前操作完成，请稍候...")


def is_shutdown_requested() -> bool:
    """检查是否请求关闭"""
    return _shutdown_requested


# ==================== 工具函数 ====================


def check_version(item_id: str, output_dir: str) -> bool:
    """检查作品版本是否为最新"""

    def _check_version_file(version_file: Path, dir_name: str = None) -> bool:
        """检查单个版本文件"""
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                version_data = json.load(f)
            current_version = version_data.get("version")

            if current_version == SCRIPT_VERSION:
                print(f"✅ 作品 {item_id} 已是最新版本 ({SCRIPT_VERSION})，跳过下载")
                if dir_name:
                    print(f"📁 找到目录: {dir_name}")
                return True
            else:
                print(
                    f"🔄 作品 {item_id} 版本不匹配 (本地: {current_version}, 当前: {SCRIPT_VERSION})，需要更新"
                )
                if dir_name:
                    print(f"📁 找到目录: {dir_name}")
                return False
        except Exception:
            return False

    try:
        output_path = Path(output_dir)

        # 首先查找原始格式的目录 {item_id}/
        version_file = output_path / item_id / "version.json"
        if version_file.exists():
            return _check_version_file(version_file)

        # 如果原始格式不存在，查找重命名格式的目录 {item_id}_*/
        for dir_path in output_path.iterdir():
            if dir_path.is_dir() and dir_path.name.startswith(f"{item_id}_"):
                version_file = dir_path / "version.json"
                if version_file.exists():
                    return _check_version_file(version_file, dir_path.name)

        # 都没找到
        return False

    except Exception as e:
        print(f"⚠️ 检查版本失败: {e}")
        return False


def save_version(item_id: str, output_dir: str):
    """保存版本信息到version.json"""
    try:
        version_file = Path(output_dir) / item_id / "version.json"
        version_file.parent.mkdir(parents=True, exist_ok=True)

        version_data = {
            "version": SCRIPT_VERSION,
            "updated_at": datetime.now().isoformat(),
            "item_id": item_id,
        }

        with open(version_file, "w", encoding="utf-8") as f:
            json.dump(version_data, f, ensure_ascii=False, indent=2)

        print(f"💾 版本信息已保存: {version_file} ({SCRIPT_VERSION})")

    except Exception as e:
        print(f"⚠️ 保存版本信息失败: {e}")


# ==================== 数据结构 ====================


class TaskType(Enum):
    PREVIEW_FILE = "preview_file"
    EXPORT_FILE = "export_file"
    THUMBNAIL = "thumbnail"
    PREVIEW_IMAGE = "preview_image"


@dataclass
class DownloadTask:
    task_type: TaskType
    url: str
    target_path: Path
    temp_path: Path
    needs_processing: bool = False
    file_name: Optional[str] = None  # 用于export下载的fileName参数


@dataclass
class ProcessingResult:
    success: bool
    task: DownloadTask
    final_path: Optional[Path] = None
    error: Optional[str] = None
    model_name: Optional[str] = None  # 新增：模型名称


@dataclass
class AssetsInfo:
    """资源信息"""

    item_id: str
    preview_live2d_zip: Optional[Dict[str, str]] = None
    export_zip_info: Optional[Dict[str, Any]] = None  # 包含itemContentId等信息
    thumbnail_image: Optional[Dict[str, str]] = None
    preview_images: List[Dict[str, str]] = None

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "AssetsInfo":
        """从API响应创建AssetsInfo"""
        assets_info = data.get("assetsInfo", {})
        item_content_details = data.get("itemContentDetails", {})

        # 提取export信息
        export_zip_info = None
        export_data_key = "書き出しデータ"
        if export_data_key in item_content_details:
            export_info = item_content_details[export_data_key]
            if ENABLE_EXPORT_ATTEMPT or export_info.get("isDownloadable", False):
                export_zip_info = {
                    "itemContentId": export_info["itemContentId"],
                    "fileSize": export_info.get("fileSize", "Unknown"),
                    "isDownloadable": True,
                }

        return cls(
            item_id=str(data.get("itemId", "")),
            preview_live2d_zip=assets_info.get("previewLive2DZip"),
            export_zip_info=export_zip_info,
            thumbnail_image=assets_info.get("thumbnailImage"),
            preview_images=assets_info.get("previewImages", []),
        )


# ==================== 安全文件管理器 ====================


class SafeFileManager:
    """安全文件操作管理器"""

    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.backup_dir = target_dir.with_name(f"{target_dir.name}_back")
        self.temp_dir = Path("models/nizima/.temp") / target_dir.name
        self.rename_callback = None  # 重命名回调函数

    def set_rename_callback(self, callback):
        """设置重命名回调函数"""
        self.rename_callback = callback

    @asynccontextmanager
    async def safe_operation(self):
        """安全操作上下文管理器"""
        try:
            # 1. 备份现有目录
            if self.target_dir.exists():
                if self.backup_dir.exists():
                    shutil.rmtree(self.backup_dir)
                shutil.move(str(self.target_dir), str(self.backup_dir))
                print(f"📦 已备份现有目录: {self.target_dir} -> {self.backup_dir}")

            # 2. 创建临时目录
            self.temp_dir.mkdir(parents=True, exist_ok=True)

            # 3. 提供上下文
            ctx = type(
                "Context",
                (),
                {"temp_dir": self.temp_dir, "target_dir": self.target_dir},
            )()

            yield ctx

            # 4. 成功时移动到最终位置
            if self.temp_dir.exists():
                self.target_dir.parent.mkdir(parents=True, exist_ok=True)

                # 移动temp_dir的内容到target_dir，而不是移动temp_dir本身
                if self.target_dir.exists():
                    shutil.rmtree(self.target_dir)

                # 重命名temp_dir为target_dir
                self.temp_dir.rename(self.target_dir)
                print(f"✅ 已移动到最终位置: {self.temp_dir} -> {self.target_dir}")

                # 如果有重命名回调，执行重命名
                if self.rename_callback:
                    new_target_dir = self.rename_callback()
                    if new_target_dir != self.target_dir:
                        self.target_dir = new_target_dir

            # 5. 删除备份
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
                print(f"🗑️ 已删除备份: {self.backup_dir}")

        except Exception as e:
            print(f"❌ 操作失败，开始回滚: {e}")

            # 回滚操作
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                print(f"🧹 已清理临时目录: {self.temp_dir}")

            if self.backup_dir.exists():
                if self.target_dir.exists():
                    shutil.rmtree(self.target_dir)
                shutil.move(str(self.backup_dir), str(self.target_dir))
                print(f"🔄 已恢复备份: {self.backup_dir} -> {self.target_dir}")

            raise


# ==================== 下载管理器 ====================


class DownloadManager:
    """并发下载管理器"""

    def __init__(self, max_concurrent: int = 5, max_retries: int = 3):
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.failed_downloads: List[Dict[str, str]] = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),
            connector=aiohttp.TCPConnector(limit=20),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def download_tasks(self, tasks: List[DownloadTask]) -> List[ProcessingResult]:
        """并发下载任务列表"""
        print(f"🚀 开始并发下载 {len(tasks)} 个任务")

        # 使用信号量控制并发
        async def download_with_semaphore(task):
            async with self.semaphore:
                return await self._download_file(task)

        # 并发执行所有下载任务
        results = await asyncio.gather(
            *[download_with_semaphore(task) for task in tasks], return_exceptions=True
        )

        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    ProcessingResult(success=False, task=tasks[i], error=str(result))
                )
            else:
                processed_results.append(result)

        success_count = sum(1 for r in processed_results if r.success)
        print(f"📊 下载完成: {success_count}/{len(tasks)} 成功")

        return processed_results

    async def _download_file(self, task: DownloadTask) -> ProcessingResult:
        """下载单个文件，支持重试"""
        # 检查是否请求关闭
        if is_shutdown_requested():
            return ProcessingResult(success=False, task=task, error="用户请求中断下载")

        # 确保目标目录存在
        task.temp_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"⬇️ 下载 {task.task_type.value}: {task.url}")

        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                if task.task_type == TaskType.EXPORT_FILE:
                    # export文件需要特殊的POST请求
                    form_data = aiohttp.FormData()
                    form_data.add_field("fileName", task.file_name or "export.zip")

                    async with self.session.post(task.url, data=form_data) as response:
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
                        async with self.session.get(
                            result["downloadUrl"]
                        ) as file_response:
                            file_response.raise_for_status()
                            content = await file_response.read()
                else:
                    # 普通GET请求
                    async with self.session.get(task.url) as response:
                        response.raise_for_status()
                        content = await response.read()

                # 写入临时文件
                with open(task.temp_path, "wb") as f:
                    f.write(content)

                print(f"✅ 下载完成: {task.temp_path.name} ({len(content):,} bytes)")

                return ProcessingResult(
                    success=True, task=task, final_path=task.temp_path
                )

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
                    # 最终失败，记录到失败列表
                    print(f"❌ 下载最终失败 {task.url}: {e}")
                    self.failed_downloads.append(
                        {
                            "url": task.url,
                            "target_path": str(task.target_path),
                            "task_type": task.task_type.value,
                            "error": str(e),
                        }
                    )

        return ProcessingResult(success=False, task=task, error=str(last_error))

    def write_failure_log(self, output_dir: Path, item_id: str = None):
        """将失败的下载记录写入日志文件"""
        if not self.failed_downloads:
            return

        log_file = output_dir / "fail_list.txt"

        # 读取现有内容（如果存在）
        existing_content = ""
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

        # 准备新内容
        new_entries = []
        for failure in self.failed_downloads:
            entry = f"""
失败记录 - {time.strftime('%Y-%m-%d %H:%M:%S')}
作品ID: {item_id or 'Unknown'}
任务类型: {failure['task_type']}
失败URL: {failure['url']}
目标路径: {failure['target_path']}
错误信息: {failure['error']}
{'='*60}"""
            new_entries.append(entry)

        # 写入文件
        with open(log_file, "w", encoding="utf-8") as f:
            if existing_content:
                f.write(existing_content)
            f.write("\n".join(new_entries))

        print(f"📝 失败记录已写入: {log_file}")
        print(f"📊 本次失败数量: {len(self.failed_downloads)}")

        # 清空失败列表
        self.failed_downloads.clear()


# ==================== 文件处理器 ====================


class FileProcessor:
    """文件处理器"""

    XOR_KEY = "AkqeZ-f,7fgx*7WU$6mWZ_98x-nWtdw4Jjky"
    ZIP_PASSWORD = "LrND6UfK(j-NmN7tTb+2S&6J56rEdfHJ3+pA"

    @classmethod
    async def process_main_file(
        cls, file_path: Path, target_dir: Path, file_type: str
    ) -> bool:
        """处理主文件（preview或export）"""
        try:
            print(f"🔧 处理{file_type}文件...")

            # 创建对应的子目录
            type_dir = target_dir / file_type
            type_dir.mkdir(parents=True, exist_ok=True)

            # 检测文件类型
            if cls._is_zip_file(file_path):
                print(f"✅ 文件已是ZIP格式")
                zip_path = file_path
            else:
                print(f"🔓 文件需要解密")
                zip_path = await cls._decrypt_file(file_path)
                if not zip_path:
                    return False

            # 解压到临时目录
            temp_extract_dir = target_dir / f".temp_{file_type}_extract"
            temp_extract_dir.mkdir(parents=True, exist_ok=True)

            success = await cls._extract_zip(zip_path, temp_extract_dir)
            if success:
                # 移动目录到目标位置，获取模型名称
                model_name = await cls._move_to_final_dir(
                    temp_extract_dir, type_dir, file_type
                )
                return model_name

            return False

        except Exception as e:
            print(f"❌ 处理{file_type}文件失败: {e}")
            return False

    @classmethod
    def _is_zip_file(cls, file_path: Path) -> bool:
        """检测文件是否为ZIP格式"""
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
                # ZIP文件的魔数
                return header in [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"]
        except Exception:
            return False

    @classmethod
    async def _decrypt_file(cls, file_path: Path) -> Optional[Path]:
        """解密文件"""
        try:
            with open(file_path, "rb") as f:
                encrypted_data = f.read()

            # XOR解密
            key_bytes = [ord(c) for c in cls.XOR_KEY]
            decrypted = bytearray()

            for i, byte in enumerate(encrypted_data):
                decrypted.append(byte ^ key_bytes[i % len(key_bytes)])

            # 保存解密后的文件
            decrypted_path = file_path.with_suffix(".zip")
            with open(decrypted_path, "wb") as f:
                f.write(decrypted)

            # 验证是否为有效的ZIP文件
            if cls._is_zip_file(decrypted_path):
                print("✅ 解密成功，确认为ZIP文件")
                return decrypted_path
            else:
                print("❌ 解密后不是有效的ZIP文件")
                return None

        except Exception as e:
            print(f"❌ 解密失败: {e}")
            return None

    @classmethod
    async def _extract_zip(cls, zip_path: Path, extract_dir: Path) -> bool:
        """解压ZIP文件"""
        try:
            print(f"📦 正在解压ZIP文件到: {extract_dir}")

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                file_count = len(zip_ref.namelist())
                print(f"📊 ZIP文件包含 {file_count} 个文件")

                # 先尝试使用密码解压
                try:
                    zip_ref.extractall(extract_dir, pwd=cls.ZIP_PASSWORD.encode())
                    print("✅ 密码解压成功")
                except Exception:
                    # 如果密码解压失败，尝试无密码解压
                    try:
                        zip_ref.extractall(extract_dir)
                        print("✅ 无密码解压成功")
                    except Exception as e:
                        print(f"❌ 解压失败: {e}")
                        return False

            return True

        except Exception as e:
            print(f"❌ 解压失败: {e}")
            return False

    @classmethod
    async def _move_to_final_dir(
        cls, extract_dir: Path, target_dir: Path, file_type: str
    ) -> Optional[str]:
        """将解压的文件移动到最终目录，返回模型名称"""
        try:
            # 查找.moc3文件确认这是Live2D模型
            moc3_files = list(extract_dir.rglob("*.moc3"))
            if moc3_files:
                moc3_file = moc3_files[0]
                model_name = moc3_file.stem
                print(f"🎭 找到Live2D模型: {model_name}")
            else:
                print("⚠️ 未找到.moc3文件")
                model_name = "unknown_model"

            # 直接使用file_type作为最终目录名（如preview、export）
            final_dir = target_dir

            # 确保目标目录的父目录存在
            final_dir.parent.mkdir(parents=True, exist_ok=True)

            # 移动目录内容
            if final_dir.exists():
                shutil.rmtree(final_dir)

            # 如果extract_dir直接包含模型文件，直接重命名
            if any(extract_dir.glob("*.moc3")):
                extract_dir.rename(final_dir)
            else:
                # 如果有子目录，移动第一个子目录的内容
                subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
                if subdirs:
                    subdirs[0].rename(final_dir)
                    # 清理空的extract_dir
                    if extract_dir.exists():
                        shutil.rmtree(extract_dir)
                else:
                    extract_dir.rename(final_dir)

            print(f"📁 {file_type}模型目录: {final_dir}")
            return model_name

        except Exception as e:
            print(f"❌ 移动目录失败: {e}")
            return None

    @classmethod
    async def process_image(cls, file_path: Path, target_dir: Path) -> bool:
        """处理图片文件"""
        try:
            # 直接复制到目标目录
            target_path = target_dir / file_path.name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target_path)
            return True
        except Exception as e:
            print(f"❌ 处理图片失败: {e}")
            return False


# ==================== 资源管理器 ====================


class AssetsManager:
    """资源信息管理器"""

    def __init__(self, item_id: str):
        self.item_id = item_id
        self.user_items_path = "https://storage.googleapis.com/market_view_useritems"

    async def get_assets_info(self) -> AssetsInfo:
        """获取资源信息"""
        api_url = f"https://nizima.com/api/items/{self.item_id}/detail"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                response.raise_for_status()

                # 检查响应类型
                content_type = response.headers.get("content-type", "")
                if "application/json" not in content_type:
                    raise ValueError(
                        f"无效的作品ID '{self.item_id}': API返回了非JSON响应 (content-type: {content_type})"
                    )

                data = await response.json()

                # 检查是否有assetsInfo
                if "assetsInfo" not in data:
                    raise ValueError(
                        f"无效的作品ID '{self.item_id}': 响应中缺少assetsInfo字段"
                    )

                print(f"📋 获取到资源信息: {self.item_id}")

                # 保存完整的API响应数据
                self._save_detail_json(data)

                return AssetsInfo.from_api_response(data), data

    def _save_detail_json(self, data: Dict[str, Any]):
        """保存详细信息到detail.json"""
        try:
            # 创建输出目录
            output_dir = Path("models/nizima") / self.item_id
            output_dir.mkdir(parents=True, exist_ok=True)

            # 保存detail.json
            detail_file = output_dir / "detail.json"
            with open(detail_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"💾 详细信息已保存: {detail_file}")

        except Exception as e:
            print(f"⚠️ 保存详细信息失败: {e}")

    def create_download_tasks(
        self, assets_info: AssetsInfo, temp_dir: Path
    ) -> List[DownloadTask]:
        """创建下载任务列表"""
        tasks = []
        downloads_dir = temp_dir / "downloads"

        # 1. Preview Live2D ZIP文件
        if assets_info.preview_live2d_zip:
            file_name = assets_info.preview_live2d_zip["fileName"]
            url = f"{self.user_items_path}/{self.item_id}/{file_name}"

            task = DownloadTask(
                task_type=TaskType.PREVIEW_FILE,
                url=url,
                target_path=temp_dir / "preview" / file_name,
                temp_path=downloads_dir / file_name,
                needs_processing=True,
            )
            tasks.append(task)
            print(f"📦 Preview文件任务: {file_name}")
        else:
            print("⚠️ 该作品没有Preview模型文件")

        # 2. Export ZIP文件（如果可下载）
        if assets_info.export_zip_info:
            item_content_id = assets_info.export_zip_info["itemContentId"]
            download_url = f"https://nizima.com/api/items/{item_content_id}/download"

            task = DownloadTask(
                task_type=TaskType.EXPORT_FILE,
                url=download_url,
                target_path=temp_dir / "export" / "export.zip",
                temp_path=downloads_dir / "export.zip",
                needs_processing=True,
                file_name="export.zip",
            )
            tasks.append(task)
            print(
                f"📦 Export文件任务: export.zip (大小: {assets_info.export_zip_info.get('fileSize', 'Unknown')}MB)"
            )

        # 3. 缩略图
        if assets_info.thumbnail_image:
            file_name = assets_info.thumbnail_image["fileName"]
            url = f"{self.user_items_path}/{self.item_id}/{file_name}"

            task = DownloadTask(
                task_type=TaskType.THUMBNAIL,
                url=url,
                target_path=temp_dir / "thumbnailImage" / file_name,
                temp_path=downloads_dir / f"thumb_{file_name}",
                needs_processing=False,
            )
            tasks.append(task)
            print(f"🖼️ 缩略图任务: {file_name}")

        # 4. 预览图片
        if assets_info.preview_images:
            for i, img_info in enumerate(assets_info.preview_images):
                file_name = img_info["fileName"]
                url = f"{self.user_items_path}/{self.item_id}/images/{file_name}"

                task = DownloadTask(
                    task_type=TaskType.PREVIEW_IMAGE,
                    url=url,
                    target_path=temp_dir / "previewImages" / file_name,
                    temp_path=downloads_dir / f"preview_{i}_{file_name}",
                    needs_processing=False,
                )
                tasks.append(task)

            print(f"🖼️ 预览图任务: {len(assets_info.preview_images)} 张")

        print(f"📋 创建了 {len(tasks)} 个下载任务")
        return tasks


# ==================== 主控制器 ====================


class NizimaFetcher:
    """Nizima下载器主控制器 v3.0"""

    def __init__(self, item_id: str, output_dir: str = "models/nizima"):
        self.item_id = str(item_id)
        self.output_dir = Path(output_dir)
        self.target_dir = self.output_dir / self.item_id
        self.model_name = None  # 存储模型名称

    def _rename_target_dir_with_model_name(self, model_name: str) -> Path:
        """根据模型名称重命名目标目录"""
        if not model_name or model_name == "unknown_model":
            return self.target_dir

        # 创建新的目录名：{id}_{model_name}
        new_dir_name = f"{self.item_id}_{model_name}"
        new_target_dir = self.output_dir / new_dir_name

        # 如果当前目录存在且新目录名不同，则重命名
        if self.target_dir.exists() and self.target_dir != new_target_dir:
            try:
                # 如果新目录已存在，先删除
                if new_target_dir.exists():
                    shutil.rmtree(new_target_dir)

                # 重命名目录
                self.target_dir.rename(new_target_dir)
                print(
                    f"📁 目录已重命名: {self.target_dir.name} -> {new_target_dir.name}"
                )

                # 更新target_dir
                self.target_dir = new_target_dir

            except Exception as e:
                print(f"⚠️ 重命名目录失败: {e}")

        return self.target_dir

    async def fetch(self) -> bool:
        """下载作品"""
        print("🚀 开始下载 Nizima 作品: {}".format(self.item_id))
        print("=" * 60)

        # 检查版本，如果已是最新版本则跳过
        if check_version(self.item_id, self.output_dir):
            return True

        # 先获取资源信息，检查是否有preview模型
        print("📋 获取资源信息...")
        assets_manager = AssetsManager(self.item_id)
        assets_info, detail_data = await assets_manager.get_assets_info()

        # 如果没有preview模型，直接跳过，不保存任何信息
        if not assets_info.preview_live2d_zip:
            print("⚠️ 该作品没有Preview模型，直接跳过")
            return False

        try:
            # 创建SafeFileManager并设置重命名回调
            safe_manager = SafeFileManager(self.target_dir)
            safe_manager.set_rename_callback(
                lambda: (
                    self._rename_target_dir_with_model_name(self.model_name)
                    if self.model_name
                    else self.target_dir
                )
            )

            async with safe_manager.safe_operation() as ctx:
                # 保存detail.json到临时目录
                detail_path = ctx.temp_dir / "detail.json"
                detail_path.parent.mkdir(parents=True, exist_ok=True)
                with open(detail_path, "w", encoding="utf-8") as f:
                    json.dump(detail_data, f, ensure_ascii=False, indent=2)
                print(f"💾 detail.json已保存到临时目录: {detail_path}")

                # 2. 创建下载任务
                print("📝 创建下载任务...")
                tasks = assets_manager.create_download_tasks(assets_info, ctx.temp_dir)

                if not tasks:
                    print("❌ 没有找到可下载的资源")
                    return False

                # 3. 并发下载
                print("⬇️ 开始并发下载...")
                async with DownloadManager(max_concurrent=5) as download_manager:
                    results = await download_manager.download_tasks(tasks)

                    # 记录失败的下载
                    if download_manager.failed_downloads:
                        download_manager.write_failure_log(
                            self.output_dir, self.item_id
                        )

                # 4. 处理文件
                print("🔧 处理下载的文件...")
                success = await self._process_results(results, ctx.temp_dir)

                if success:
                    print("✅ 所有操作完成")

                    # 如果有模型名称，更新版本信息中的模型名称
                    model_name_for_version = (
                        self.model_name if self.model_name else "unknown"
                    )

                    # 保存版本信息到临时目录
                    version_file = ctx.temp_dir / "version.json"
                    version_data = {
                        "version": SCRIPT_VERSION,
                        "updated_at": datetime.now().isoformat(),
                        "item_id": self.item_id,
                        "model_name": model_name_for_version,
                    }
                    with open(version_file, "w", encoding="utf-8") as f:
                        json.dump(version_data, f, ensure_ascii=False, indent=2)
                    print(f"💾 版本信息已保存: {version_file} ({SCRIPT_VERSION})")
                    return True
                else:
                    print("❌ 处理过程中出现错误")
                    return False

        except Exception as e:
            print(f"❌ 下载失败: {e}")
            return False

    async def _process_results(
        self, results: List[ProcessingResult], temp_dir: Path
    ) -> bool:
        """处理下载结果"""
        success_count = 0
        total_count = len(results)

        for result in results:
            if not result.success:
                print(f"⚠️ 跳过失败的任务: {result.task.task_type.value}")
                continue

            try:
                if result.task.task_type == TaskType.PREVIEW_FILE:
                    model_name = await FileProcessor.process_main_file(
                        result.final_path, temp_dir, "preview"
                    )
                    if model_name:
                        result.model_name = model_name
                        print("✅ Preview文件处理完成")
                        success_count += 1

                elif result.task.task_type == TaskType.EXPORT_FILE:
                    success = await FileProcessor.process_main_file(
                        result.final_path, temp_dir, "export"
                    )
                    if success:
                        print("✅ Export文件处理完成")
                        success_count += 1

                elif result.task.task_type == TaskType.THUMBNAIL:
                    target_dir = temp_dir / "thumbnailImage"
                    success = await FileProcessor.process_image(
                        result.final_path, target_dir
                    )
                    if success:
                        print(f"✅ 图片处理完成: {result.final_path.name}")
                        success_count += 1

                elif result.task.task_type == TaskType.PREVIEW_IMAGE:
                    target_dir = temp_dir / "previewImages"
                    success = await FileProcessor.process_image(
                        result.final_path, target_dir
                    )
                    if success:
                        print(f"✅ 图片处理完成: {result.final_path.name}")
                        success_count += 1

            except Exception as e:
                print(f"❌ 处理文件失败 {result.final_path}: {e}")

        print(f"📊 处理结果: {success_count}/{total_count} 成功")

        # 提取模型名称并重命名目录
        model_name = None
        for result in results:
            if result.success and result.model_name:
                model_name = result.model_name
                break

        if model_name:
            self.model_name = model_name
            print(f"🎭 提取到模型名称: {model_name}")

        return success_count > 0


# ==================== 批量下载 ====================


async def fetch_multiple_items(
    item_ids: List[str], output_dir: str = "models/nizima", max_concurrent: int = 3
) -> None:
    """批量下载多个作品"""
    print(f"🚀 开始并发下载 {len(item_ids)} 个作品")
    print(f"📋 作品列表: {', '.join(item_ids)}")
    print(f"🔧 最大并发数: {max_concurrent}")
    print("=" * 80)

    # 创建信号量控制并发数
    semaphore = asyncio.Semaphore(max_concurrent)

    async def download_single(item_id: str) -> bool:
        """下载单个作品"""
        async with semaphore:
            # 检查是否请求关闭
            if is_shutdown_requested():
                print(f"🛑 跳过作品 {item_id}（用户请求中断）")
                return False

            print(f"\n🎯 开始处理作品: {item_id}")
            try:
                fetcher = NizimaFetcher(item_id, output_dir)
                success = await fetcher.fetch()
                if success:
                    print(f"✅ 作品 {item_id} 下载成功")
                    return True
                else:
                    print(f"❌ 作品 {item_id} 下载失败")
                    return False
            except KeyboardInterrupt:
                print(f"🛑 作品 {item_id} 被用户中断")
                return False
            except Exception as e:
                print(f"❌ 作品 {item_id} 下载异常: {e}")
                return False

    # 执行并发下载
    results = await asyncio.gather(
        *[download_single(item_id) for item_id in item_ids], return_exceptions=True
    )

    # 统计结果
    successful = 0
    failed_items = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ 作品 {item_ids[i]} 发生异常: {result}")
            failed_items.append(item_ids[i])
        elif result:
            successful += 1
        else:
            failed_items.append(item_ids[i])

    # 输出总结
    print("\n" + "=" * 80)
    print("📊 批量下载完成")
    print("=" * 80)
    print(f"✅ 成功: {successful}/{len(item_ids)} 个作品")

    if failed_items:
        print(f"❌ 失败: {len(failed_items)} 个作品")
        print(f"失败列表: {', '.join(failed_items)}")
    else:
        print("🎉 所有作品下载完成!")


# ==================== 命令行接口 ====================


async def main():
    """主函数"""
    import argparse

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="Nizima Live2D模型下载器 v3.0")
    parser.add_argument("item_ids", nargs="+", help="作品ID列表")
    parser.add_argument("--output", "-o", default="models/nizima", help="输出目录")
    parser.add_argument("--concurrent", "-c", type=int, default=3, help="最大并发数")

    args = parser.parse_args()

    try:
        if len(args.item_ids) == 1:
            # 单个作品下载
            fetcher = NizimaFetcher(args.item_ids[0], args.output)
            success = await fetcher.fetch()

            if is_shutdown_requested():
                print("\n🛑 下载被用户中断")
            elif success:
                print(
                    f"\n🎉 下载完成! 文件保存在: {Path(args.output) / args.item_ids[0]}"
                )
            else:
                print("\n❌ 下载失败")
        else:
            # 批量下载
            await fetch_multiple_items(
                list(set(args.item_ids)), args.output, args.concurrent
            )

            if is_shutdown_requested():
                print("\n🛑 批量下载被用户中断")
                print("💡 提示：已完成的下载会被保留，未完成的可以重新运行")

    except KeyboardInterrupt:
        print("\n🛑 下载被用户中断")
        print("💡 提示：系统已安全清理，可以重新运行")


if __name__ == "__main__":
    asyncio.run(main())

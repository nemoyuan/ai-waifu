"""
任务工厂实现

根据资源信息创建完整的任务图
"""

import sys
from pathlib import Path
from typing import Any, Dict

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tasks import (
    DecryptTask,
    DownloadTask,
    ExtractTask,
    ProcessImagesTask,
    RenameDirectoryTask,
    SaveDetailJsonTask,
    SaveVersionTask,
)

from .graph import TaskGraph


class TaskFactory:
    """任务工厂

    根据输入信息创建完整的任务图
    """

    def __init__(self, item_id: str, base_output_dir: Path, temp_dir: Path):
        """初始化任务工厂

        Args:
            item_id: 作品ID
            base_output_dir: 基础输出目录 (如 models/nizima/)
            temp_dir: 临时工作目录
        """
        self.item_id = item_id
        self.base_output_dir = Path(base_output_dir)
        self.temp_dir = Path(temp_dir)

    async def create_task_graph(
        self, assets_info: "AssetsInfo", detail_data: Dict[str, Any]
    ) -> TaskGraph:
        """根据资源信息创建任务图

        Args:
            assets_info: 资源信息
            detail_data: 详细数据

        Returns:
            TaskGraph: 构建好的任务图
        """
        graph = TaskGraph()

        # 创建关键目录路径
        downloads_dir = self.temp_dir / "downloads"
        decrypted_dir = self.temp_dir / "decrypted"
        extracted_dir = self.temp_dir / "extracted"

        # 确保目录存在
        for dir_path in [downloads_dir, decrypted_dir, extracted_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # 1. 保存detail.json任务
        save_detail_task = SaveDetailJsonTask(
            task_id=f"save_detail_{self.item_id}",
            output_path=self.temp_dir / "detail.json",
            data=detail_data,
        )
        graph.add_task(save_detail_task)

        # 2. Preview相关任务
        preview_extract_task = None
        if assets_info.preview_live2d_zip:
            preview_extract_task = await self._create_preview_tasks(
                graph, assets_info, downloads_dir, decrypted_dir, extracted_dir
            )

        # 3. Export相关任务（如果可用）
        export_extract_task = None
        if assets_info.export_zip_info:
            export_extract_task = await self._create_export_tasks(
                graph, assets_info, downloads_dir, decrypted_dir, extracted_dir
            )

        # 4. 图片相关任务
        await self._create_image_tasks(graph, assets_info, downloads_dir)

        # 5. 重命名目录任务（依赖preview解压任务获取模型名）
        rename_deps = []
        if preview_extract_task:
            rename_deps.append(preview_extract_task.task_id)
        if export_extract_task:
            rename_deps.append(export_extract_task.task_id)

        rename_task = None
        if rename_deps:
            rename_task = RenameDirectoryTask(
                task_id=f"rename_dir_{self.item_id}",
                temp_dir=self.temp_dir,
                base_output_dir=self.base_output_dir,
                item_id=self.item_id,
                model_name_source_task_id=(
                    preview_extract_task.task_id if preview_extract_task else ""
                ),
                deps_on=rename_deps,
            )
            graph.add_task(rename_task)

        # 6. 保存版本信息任务
        version_deps = [save_detail_task.task_id]
        if rename_task:
            version_deps.append(rename_task.task_id)

        save_version_task = SaveVersionTask(
            task_id=f"save_version_{self.item_id}",
            output_path=self.temp_dir / "version.json",
            item_id=self.item_id,
            script_version="v4",
            deps_on=version_deps,
        )
        graph.add_task(save_version_task)

        return graph

    async def _create_preview_tasks(
        self,
        graph: TaskGraph,
        assets_info: "AssetsInfo",
        downloads_dir: Path,
        decrypted_dir: Path,
        extracted_dir: Path,
    ) -> "ExtractTask":
        """创建Preview相关任务"""
        file_name = assets_info.preview_live2d_zip["fileName"]
        url = f"https://storage.googleapis.com/market_view_useritems/{self.item_id}/{file_name}"

        # 下载任务
        download_task = DownloadTask(
            task_id=f"download_preview_{self.item_id}",
            url=url,
            target_path=downloads_dir / file_name,
        )
        graph.add_task(download_task)

        # 解密任务
        decrypt_task = DecryptTask(
            task_id=f"decrypt_preview_{self.item_id}",
            input_file=downloads_dir / file_name,
            output_file=decrypted_dir / f"preview_{self.item_id}.zip",
            deps_on=[download_task.task_id],
        )
        graph.add_task(decrypt_task)

        # 解压任务
        extract_task = ExtractTask(
            task_id=f"extract_preview_{self.item_id}",
            input_file=decrypted_dir / f"preview_{self.item_id}.zip",
            output_dir=self.temp_dir / "preview",
            deps_on=[decrypt_task.task_id],
        )
        graph.add_task(extract_task)

        return extract_task

    async def _create_export_tasks(
        self,
        graph: TaskGraph,
        assets_info: "AssetsInfo",
        downloads_dir: Path,
        decrypted_dir: Path,
        extracted_dir: Path,
    ) -> "ExtractTask":
        """创建Export相关任务"""
        item_content_id = assets_info.export_zip_info["itemContentId"]
        download_url = f"https://nizima.com/api/items/{item_content_id}/download"

        # 下载任务
        download_task = DownloadTask(
            task_id=f"download_export_{self.item_id}",
            url=download_url,
            target_path=downloads_dir / "export.zip",
            file_name="export.zip",
            is_export=True,
        )
        graph.add_task(download_task)

        # 解密任务
        decrypt_task = DecryptTask(
            task_id=f"decrypt_export_{self.item_id}",
            input_file=downloads_dir / "export.zip",
            output_file=decrypted_dir / f"export_{self.item_id}.zip",
            deps_on=[download_task.task_id],
        )
        graph.add_task(decrypt_task)

        # 解压任务
        extract_task = ExtractTask(
            task_id=f"extract_export_{self.item_id}",
            input_file=decrypted_dir / f"export_{self.item_id}.zip",
            output_dir=self.temp_dir / "export",
            deps_on=[decrypt_task.task_id],
        )
        graph.add_task(extract_task)

        return extract_task

    async def _create_image_tasks(
        self, graph: TaskGraph, assets_info: "AssetsInfo", downloads_dir: Path
    ):
        """创建图片相关任务"""
        # 缩略图任务
        if assets_info.thumbnail_image:
            file_name = assets_info.thumbnail_image["fileName"]
            url = f"https://storage.googleapis.com/market_view_useritems/{self.item_id}/{file_name}"

            download_task = DownloadTask(
                task_id=f"download_thumb_{self.item_id}",
                url=url,
                target_path=downloads_dir / f"thumb_{file_name}",
            )
            graph.add_task(download_task)

            process_task = ProcessImagesTask(
                task_id=f"process_thumb_{self.item_id}",
                input_file=downloads_dir / f"thumb_{file_name}",
                output_file=self.temp_dir / "thumbnailImage" / file_name,
                deps_on=[download_task.task_id],
            )
            graph.add_task(process_task)

        # 预览图任务
        if assets_info.preview_images:
            for i, img_info in enumerate(assets_info.preview_images):
                file_name = img_info["fileName"]
                url = f"https://storage.googleapis.com/market_view_useritems/{self.item_id}/images/{file_name}"

                download_task = DownloadTask(
                    task_id=f"download_preview_img_{i}_{self.item_id}",
                    url=url,
                    target_path=downloads_dir / f"preview_{i}_{file_name}",
                )
                graph.add_task(download_task)

                process_task = ProcessImagesTask(
                    task_id=f"process_preview_img_{i}_{self.item_id}",
                    input_file=downloads_dir / f"preview_{i}_{file_name}",
                    output_file=self.temp_dir / "previewImages" / file_name,
                    deps_on=[download_task.task_id],
                )
                graph.add_task(process_task)

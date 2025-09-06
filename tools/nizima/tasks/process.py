"""
文件处理任务实现

负责处理图片文件和重命名目录等操作
"""

import shutil
from pathlib import Path
from typing import Any

from .base import Task


class ProcessImagesTask(Task):
    """图片处理任务

    将下载的图片文件移动到最终目录
    """

    def __init__(
        self, task_id: str, input_file: Path, output_file: Path, deps_on: list = None
    ):
        """初始化图片处理任务

        Args:
            task_id: 任务ID
            input_file: 输入文件路径
            output_file: 输出文件路径
            deps_on: 依赖的任务ID列表
        """
        super().__init__(task_id, deps_on)
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)

    def is_completed(self) -> bool:
        """检查图片是否已处理"""
        return self.output_file.exists() and self.output_file.stat().st_size > 0

    async def execute(self) -> Path:
        """执行图片处理"""
        print(f"🖼️ 处理图片: {self.input_file.name}")

        try:
            # 确保输出目录存在
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件到目标位置
            shutil.copy2(self.input_file, self.output_file)

            print(f"✅ 图片处理完成: {self.output_file.name}")
            self.mark_completed(self.output_file)
            return self.output_file

        except Exception as e:
            error_msg = f"处理图片失败: {e}"
            print(f"❌ {error_msg}")
            self.mark_failed(error_msg)
            raise Exception(error_msg)


class RenameDirectoryTask(Task):
    """重命名目录任务

    根据模型名称重命名最终目录
    """

    def __init__(
        self,
        task_id: str,
        temp_dir: Path,
        base_output_dir: Path,
        item_id: str,
        model_name_source_task_id: str,
        deps_on: list = None,
    ):
        """初始化重命名目录任务

        Args:
            task_id: 任务ID
            temp_dir: 临时工作目录
            base_output_dir: 基础输出目录
            item_id: 作品ID
            model_name_source_task_id: 提供模型名称的任务ID
            deps_on: 依赖的任务ID列表
        """
        super().__init__(task_id, deps_on)
        self.temp_dir = Path(temp_dir)
        self.base_output_dir = Path(base_output_dir)
        self.item_id = item_id
        self.model_name_source_task_id = model_name_source_task_id
        self._final_dir = None

    def is_completed(self) -> bool:
        """检查是否已重命名"""
        # 这个任务总是需要执行，因为它负责最终的目录移动
        return False

    async def execute(self) -> Path:
        """执行目录重命名

        Returns:
            Path: 最终的目标目录路径
        """
        print(f"📁 准备重命名目录...")

        try:
            # 从依赖任务获取模型名称
            model_name = getattr(self, "model_name", "unknown_model")

            # 创建新的目录名：{id}_{model_name}
            if model_name and model_name != "unknown_model":
                new_dir_name = f"{self.item_id}_{model_name}"
            else:
                new_dir_name = self.item_id

            final_dir = self.base_output_dir / new_dir_name

            # 确保基础输出目录存在
            self.base_output_dir.mkdir(parents=True, exist_ok=True)

            # 如果最终目录已存在，先删除
            if final_dir.exists():
                shutil.rmtree(final_dir)

            # 移动临时目录到最终位置
            shutil.move(str(self.temp_dir), str(final_dir))

            print(f"✅ 目录已移动: {self.temp_dir.name} -> {final_dir.name}")

            self._final_dir = final_dir
            self.mark_completed(final_dir)
            return final_dir

        except Exception as e:
            error_msg = f"重命名目录失败: {e}"
            print(f"❌ {error_msg}")
            self.mark_failed(error_msg)
            raise Exception(error_msg)

    def set_model_name(self, model_name: str):
        """设置模型名称（由TaskScheduler调用）"""
        self.model_name = model_name

    @property
    def final_dir(self) -> Path:
        """获取最终目录路径"""
        return self._final_dir

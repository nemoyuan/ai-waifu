"""
解压任务实现

负责解压ZIP文件到指定目录
"""

import zipfile
from pathlib import Path
from typing import Any

from .base import Task


class ExtractTask(Task):
    """解压任务
    
    解压ZIP文件到指定目录
    """
    
    ZIP_PASSWORD = "LrND6UfK(j-NmN7tTb+2S&6J56rEdfHJ3+pA"
    
    def __init__(
        self,
        task_id: str,
        input_file: Path,
        output_dir: Path,
        deps_on: list = None
    ):
        """初始化解压任务
        
        Args:
            task_id: 任务ID
            input_file: 输入ZIP文件路径
            output_dir: 输出目录路径
            deps_on: 依赖的任务ID列表
        """
        super().__init__(task_id, deps_on)
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        
    def is_completed(self) -> bool:
        """检查是否已解压"""
        if not self.output_dir.exists():
            return False
            
        # 检查是否包含关键文件（如.moc3文件）
        moc3_files = list(self.output_dir.rglob("*.moc3"))
        return len(moc3_files) > 0
        
    async def execute(self) -> dict:
        """执行解压
        
        Returns:
            dict: 包含解压信息的字典，如 {"output_dir": Path, "model_name": str}
        """
        print(f"📦 解压ZIP文件: {self.input_file.name}")
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(self.input_file, "r") as zip_ref:
                file_count = len(zip_ref.namelist())
                print(f"📊 ZIP文件包含 {file_count} 个文件")
                
                # 先尝试使用密码解压
                try:
                    zip_ref.extractall(self.output_dir, pwd=self.ZIP_PASSWORD.encode())
                    print("✅ 密码解压成功")
                except Exception:
                    # 如果密码解压失败，尝试无密码解压
                    try:
                        zip_ref.extractall(self.output_dir)
                        print("✅ 无密码解压成功")
                    except Exception as e:
                        error_msg = f"解压失败: {e}"
                        print(f"❌ {error_msg}")
                        self.mark_failed(error_msg)
                        raise Exception(error_msg)
                        
            # 查找模型名称
            model_name = self._find_model_name()
            
            result = {
                "output_dir": self.output_dir,
                "model_name": model_name
            }
            
            print(f"✅ 解压完成: {self.output_dir}")
            if model_name:
                print(f"🎭 找到Live2D模型: {model_name}")
                
            self.mark_completed(result)
            return result
            
        except Exception as e:
            if not isinstance(e, Exception) or "解压失败" not in str(e):
                error_msg = f"解压失败: {e}"
                print(f"❌ {error_msg}")
                self.mark_failed(error_msg)
            raise
            
    def _find_model_name(self) -> str:
        """查找模型名称"""
        try:
            # 查找.moc3文件确认这是Live2D模型
            moc3_files = list(self.output_dir.rglob("*.moc3"))
            if moc3_files:
                model_name = moc3_files[0].stem
                return model_name
            else:
                print("⚠️ 未找到.moc3文件")
                return "unknown_model"
        except Exception as e:
            print(f"⚠️ 查找模型名称失败: {e}")
            return "unknown_model"

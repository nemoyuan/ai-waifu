"""
保存任务实现

负责保存版本信息和详细信息等数据
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .base import Task


class SaveDetailJsonTask(Task):
    """保存详细信息任务
    
    将API返回的原始数据保存到detail.json
    """
    
    def __init__(
        self,
        task_id: str,
        output_path: Path,
        data: Dict[str, Any],
        deps_on: list = None
    ):
        """初始化保存详细信息任务
        
        Args:
            task_id: 任务ID
            output_path: 输出文件路径
            data: 要保存的数据
            deps_on: 依赖的任务ID列表
        """
        super().__init__(task_id, deps_on)
        self.output_path = Path(output_path)
        self.data = data
        
    def is_completed(self) -> bool:
        """检查detail.json是否已存在"""
        return self.output_path.exists() and self.output_path.stat().st_size > 0
        
    async def execute(self) -> Path:
        """执行保存详细信息"""
        print(f"💾 保存详细信息: {self.output_path.name}")
        
        try:
            # 确保输出目录存在
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存数据到JSON文件
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                
            print(f"✅ 详细信息已保存: {self.output_path}")
            self.mark_completed(self.output_path)
            return self.output_path
            
        except Exception as e:
            error_msg = f"保存详细信息失败: {e}"
            print(f"❌ {error_msg}")
            self.mark_failed(error_msg)
            raise Exception(error_msg)


class SaveVersionTask(Task):
    """保存版本信息任务
    
    将版本信息保存到version.json
    """
    
    def __init__(
        self,
        task_id: str,
        output_path: Path,
        item_id: str,
        script_version: str,
        model_name: str = None,
        deps_on: list = None
    ):
        """初始化保存版本信息任务
        
        Args:
            task_id: 任务ID
            output_path: 输出文件路径
            item_id: 作品ID
            script_version: 脚本版本
            model_name: 模型名称
            deps_on: 依赖的任务ID列表
        """
        super().__init__(task_id, deps_on)
        self.output_path = Path(output_path)
        self.item_id = item_id
        self.script_version = script_version
        self.model_name = model_name
        
    def is_completed(self) -> bool:
        """检查version.json是否已存在且版本匹配"""
        if not self.output_path.exists():
            return False
            
        try:
            with open(self.output_path, "r", encoding="utf-8") as f:
                version_data = json.load(f)
            current_version = version_data.get("version")
            return current_version == self.script_version
        except Exception:
            return False
            
    async def execute(self) -> Path:
        """执行保存版本信息"""
        print(f"💾 保存版本信息: {self.output_path.name}")
        
        try:
            # 确保输出目录存在
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 准备版本数据
            version_data = {
                "version": self.script_version,
                "updated_at": datetime.now().isoformat(),
                "item_id": self.item_id,
            }
            
            if self.model_name:
                version_data["model_name"] = self.model_name
                
            # 保存版本信息
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(version_data, f, ensure_ascii=False, indent=2)
                
            print(f"✅ 版本信息已保存: {self.output_path} ({self.script_version})")
            self.mark_completed(self.output_path)
            return self.output_path
            
        except Exception as e:
            error_msg = f"保存版本信息失败: {e}"
            print(f"❌ {error_msg}")
            self.mark_failed(error_msg)
            raise Exception(error_msg)
            
    def set_model_name(self, model_name: str):
        """设置模型名称（由TaskScheduler调用）"""
        self.model_name = model_name

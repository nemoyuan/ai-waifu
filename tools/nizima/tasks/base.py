"""
任务基类定义

定义了所有任务的抽象接口和通用行为
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Optional


class Task(ABC):
    """任务抽象基类
    
    每个任务都是一个独立的工作单元，具有：
    - 唯一标识符 (task_id)
    - 依赖关系 (deps_on)
    - 完成状态检查 (is_completed)
    - 执行逻辑 (execute)
    """
    
    def __init__(self, task_id: str, deps_on: List[str] = None):
        """初始化任务
        
        Args:
            task_id: 唯一标识符，如 "download_preview_12345"
            deps_on: 依赖的任务ID列表
        """
        self.task_id = task_id
        self.deps_on = deps_on or []
        self._completed = False
        self._result = None
        self._error = None
        
    @abstractmethod
    def is_completed(self) -> bool:
        """检查任务的输出是否已存在
        
        如果输出已存在，则认为任务已完成，可以跳过执行。
        这是实现增量执行的关键。
        
        Returns:
            bool: 任务是否已完成
        """
        pass
        
    @abstractmethod
    async def execute(self) -> Any:
        """执行任务的具体逻辑
        
        执行成功后，应设置 self._completed = True 并存储 self._result。
        如果执行失败，应抛出异常或设置 self._error。
        
        Returns:
            Any: 执行结果，可以是文件路径、模型名、布尔值等
        """
        pass
        
    @property
    def result(self) -> Any:
        """获取任务执行结果"""
        return self._result
        
    @property
    def completed(self) -> bool:
        """获取任务完成状态"""
        return self._completed
        
    @property
    def error(self) -> Optional[str]:
        """获取任务错误信息"""
        return self._error
        
    def mark_completed(self, result: Any = None):
        """标记任务为已完成
        
        Args:
            result: 任务执行结果
        """
        self._completed = True
        self._result = result
        
    def mark_failed(self, error: str):
        """标记任务为失败
        
        Args:
            error: 错误信息
        """
        self._completed = False
        self._error = error
        
    def __str__(self) -> str:
        """字符串表示"""
        status = "✅" if self._completed else "⏳"
        deps = f" (deps: {self.deps_on})" if self.deps_on else ""
        return f"{status} {self.task_id}{deps}"
        
    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"Task(id={self.task_id}, deps={self.deps_on}, completed={self._completed})"


# 全局中断标志
_shutdown_requested = False


def request_shutdown():
    """请求关闭所有任务"""
    global _shutdown_requested
    _shutdown_requested = True


def is_shutdown_requested() -> bool:
    """检查是否请求关闭"""
    return _shutdown_requested


def reset_shutdown_flag():
    """重置关闭标志"""
    global _shutdown_requested
    _shutdown_requested = False

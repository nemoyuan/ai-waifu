"""
任务图实现

管理任务之间的依赖关系和执行顺序
"""

import sys
from pathlib import Path
from typing import Dict, List, Set

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from tasks.base import Task


class TaskGraph:
    """任务图

    由多个Task节点和它们之间的依赖关系构成的有向无环图(DAG)
    """

    def __init__(self):
        """初始化任务图"""
        self.tasks: Dict[str, Task] = {}  # task_id -> Task实例

    def add_task(self, task: Task):
        """添加任务到图中

        Args:
            task: 要添加的任务
        """
        self.tasks[task.task_id] = task

    def get_task(self, task_id: str) -> Task:
        """获取指定任务

        Args:
            task_id: 任务ID

        Returns:
            Task: 任务实例
        """
        return self.tasks.get(task_id)

    def get_dependencies(self, task_id: str) -> List[str]:
        """获取指定任务的所有直接依赖

        Args:
            task_id: 任务ID

        Returns:
            List[str]: 依赖的任务ID列表
        """
        task = self.tasks.get(task_id)
        return task.deps_on if task else []

    def get_dependents(self, task_id: str) -> List[str]:
        """获取依赖于指定任务的所有任务ID

        Args:
            task_id: 任务ID

        Returns:
            List[str]: 依赖于该任务的任务ID列表
        """
        dependents = []
        for tid, task in self.tasks.items():
            if task_id in task.deps_on:
                dependents.append(tid)
        return dependents

    def get_ready_tasks(self) -> List[str]:
        """获取当前所有依赖都已满足且未完成的任务ID

        Returns:
            List[str]: 可以执行的任务ID列表
        """
        ready = []
        for task_id, task in self.tasks.items():
            if not task.completed:
                # 检查所有依赖是否都已完成
                all_deps_completed = all(
                    self.tasks[dep_id].completed
                    for dep_id in task.deps_on
                    if dep_id in self.tasks
                )
                if all_deps_completed:
                    ready.append(task_id)
        return ready

    def is_all_completed(self) -> bool:
        """检查是否所有任务都已完成

        Returns:
            bool: 是否所有任务都已完成
        """
        return all(task.completed for task in self.tasks.values())

    def get_completion_stats(self) -> Dict[str, int]:
        """获取完成统计信息

        Returns:
            Dict[str, int]: 包含总数、完成数、失败数的统计
        """
        total = len(self.tasks)
        completed = sum(1 for task in self.tasks.values() if task.completed)
        failed = sum(1 for task in self.tasks.values() if task.error)

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": total - completed,
        }

    def validate_dependencies(self) -> List[str]:
        """验证依赖关系是否有效

        Returns:
            List[str]: 错误信息列表，空列表表示无错误
        """
        errors = []

        # 检查依赖的任务是否存在
        for task_id, task in self.tasks.items():
            for dep_id in task.deps_on:
                if dep_id not in self.tasks:
                    errors.append(f"任务 {task_id} 依赖的任务 {dep_id} 不存在")

        # 检查是否有循环依赖
        if self._has_cycle():
            errors.append("检测到循环依赖")

        return errors

    def _has_cycle(self) -> bool:
        """检查是否有循环依赖（使用DFS）

        Returns:
            bool: 是否有循环依赖
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        colors = {task_id: WHITE for task_id in self.tasks}

        def dfs(task_id: str) -> bool:
            if colors[task_id] == GRAY:
                return True  # 发现后向边，存在循环
            if colors[task_id] == BLACK:
                return False  # 已经访问过

            colors[task_id] = GRAY

            for dep_id in self.tasks[task_id].deps_on:
                if dep_id in self.tasks and dfs(dep_id):
                    return True

            colors[task_id] = BLACK
            return False

        for task_id in self.tasks:
            if colors[task_id] == WHITE:
                if dfs(task_id):
                    return True

        return False

    def __str__(self) -> str:
        """字符串表示"""
        lines = [f"TaskGraph ({len(self.tasks)} tasks):"]
        for task_id, task in self.tasks.items():
            status = "✅" if task.completed else "⏳"
            deps = f" <- {task.deps_on}" if task.deps_on else ""
            lines.append(f"  {status} {task_id}{deps}")
        return "\n".join(lines)

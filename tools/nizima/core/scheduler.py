"""
任务调度器实现

负责执行任务图中的任务，支持并发执行和优雅退出
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tasks.base import is_shutdown_requested, Task

from .graph import TaskGraph


class TaskScheduler:
    """任务调度器

    负责执行整个任务图，支持并发执行和依赖管理
    """

    def __init__(self, max_concurrent: int = 5):
        """初始化调度器

        Args:
            max_concurrent: 最大并发任务数
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.task_results: Dict[str, Any] = {}  # 存储任务执行结果

    async def execute_graph(self, graph: TaskGraph) -> bool:
        """执行整个任务图

        Args:
            graph: 要执行的任务图

        Returns:
            bool: 是否成功执行完所有任务
        """
        print(f"🚀 开始执行任务图，共 {len(graph.tasks)} 个任务")

        # 验证任务图
        errors = graph.validate_dependencies()
        if errors:
            print("❌ 任务图验证失败:")
            for error in errors:
                print(f"  - {error}")
            return False

        try:
            while not graph.is_all_completed():
                # 检查是否请求关闭
                if is_shutdown_requested():
                    print("🛑 收到关闭请求，停止执行任务图")
                    return False

                # 获取当前可执行的任务
                ready_task_ids = graph.get_ready_tasks()

                if not ready_task_ids:
                    # 如果没有ready任务但图未完成，说明存在问题
                    incomplete_tasks = [
                        tid for tid, t in graph.tasks.items() if not t.completed
                    ]
                    failed_tasks = [tid for tid, t in graph.tasks.items() if t.error]

                    if failed_tasks:
                        print(f"❌ 存在失败的任务，无法继续: {failed_tasks}")
                    else:
                        print(
                            f"❌ 无法继续执行，存在未完成且无ready任务的情况: {incomplete_tasks}"
                        )
                    return False

                # 并发执行所有ready任务
                print(f"📋 找到 {len(ready_task_ids)} 个可执行任务: {ready_task_ids}")

                # 执行任务并收集结果
                results = await asyncio.gather(
                    *[self._execute_single_task(graph, tid) for tid in ready_task_ids],
                    return_exceptions=True,
                )

                # 处理执行结果
                for i, result in enumerate(results):
                    task_id = ready_task_ids[i]
                    if isinstance(result, Exception):
                        print(f"❌ 任务 {task_id} 执行异常: {result}")
                        graph.tasks[task_id].mark_failed(str(result))
                    else:
                        self.task_results[task_id] = result

            # 输出完成统计
            stats = graph.get_completion_stats()
            print(f"📊 任务执行完成: {stats['completed']}/{stats['total']} 成功")

            if stats["failed"] > 0:
                print(f"⚠️ 失败任务数: {stats['failed']}")
                return False

            print("🎉 所有任务执行完毕！")
            return True

        except Exception as e:
            print(f"❌ 执行任务图时发生异常: {e}")
            return False

    async def _execute_single_task(self, graph: TaskGraph, task_id: str) -> Any:
        """执行单个任务

        Args:
            graph: 任务图
            task_id: 任务ID

        Returns:
            Any: 任务执行结果
        """
        async with self.semaphore:  # 控制并发数
            task = graph.tasks[task_id]

            # 再次检查是否已完成（防止并发冲突）
            if task.completed:
                print(f"✅ 任务 {task_id} 已完成（跳过）")
                return task.result

            # 检查依赖是否真的都完成了（双重保险）
            for dep_id in task.deps_on:
                if dep_id in graph.tasks and not graph.tasks[dep_id].completed:
                    raise RuntimeError(f"任务 {task_id} 的依赖 {dep_id} 未完成")

            # 检查输出是否存在，决定是否跳过
            if task.is_completed():
                print(f"✅ 任务 {task_id} 输出已存在（跳过执行）")
                task.mark_completed()
                # 尝试从现有输出恢复结果
                return await self._recover_task_result(task)

            print(f"▶️ 开始执行任务: {task_id}")

            try:
                # 为任务提供依赖任务的结果
                await self._prepare_task_dependencies(graph, task)

                # 执行任务
                result = await task.execute()

                print(f"✅ 任务 {task_id} 执行成功")
                return result

            except Exception as e:
                print(f"❌ 任务 {task_id} 执行失败: {e}")
                task.mark_failed(str(e))
                raise

    async def _prepare_task_dependencies(self, graph: TaskGraph, task: Task):
        """为任务准备依赖信息

        Args:
            graph: 任务图
            task: 要准备的任务
        """
        # 为特定类型的任务提供依赖任务的结果
        from tasks.process import RenameDirectoryTask
        from tasks.save import SaveVersionTask

        if isinstance(task, RenameDirectoryTask):
            # 为重命名任务提供模型名称
            for dep_id in task.deps_on:
                dep_task = graph.tasks.get(dep_id)
                if dep_task and dep_task.completed and dep_task.result:
                    if (
                        isinstance(dep_task.result, dict)
                        and "model_name" in dep_task.result
                    ):
                        task.set_model_name(dep_task.result["model_name"])
                        break

        elif isinstance(task, SaveVersionTask):
            # 为版本保存任务提供模型名称
            model_name = None
            for dep_id in task.deps_on:
                dep_task = graph.tasks.get(dep_id)
                if dep_task and dep_task.completed and dep_task.result:
                    if (
                        isinstance(dep_task.result, dict)
                        and "model_name" in dep_task.result
                    ):
                        model_name = dep_task.result["model_name"]
                        break
            if model_name:
                task.set_model_name(model_name)

    async def _recover_task_result(self, task: Task) -> Any:
        """从已存在的输出恢复任务结果

        Args:
            task: 任务实例

        Returns:
            Any: 恢复的结果
        """
        # 对于不同类型的任务，尝试恢复其结果
        from tasks.extract import ExtractTask

        if isinstance(task, ExtractTask):
            # 尝试恢复解压任务的结果
            model_name = task._find_model_name()
            return {"output_dir": task.output_dir, "model_name": model_name}

        # 默认返回None
        return None

    def get_task_result(self, task_id: str) -> Any:
        """获取任务执行结果

        Args:
            task_id: 任务ID

        Returns:
            Any: 任务执行结果
        """
        return self.task_results.get(task_id)

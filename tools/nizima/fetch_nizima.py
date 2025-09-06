#!/usr/bin/env python3
"""
Nizima Live2D模型下载器 v4.0
基于任务图（Task Graph）的全新架构

特性：
- 模块化任务设计
- 智能依赖管理
- 并发执行支持
- 增量下载（跳过已存在的输出）
- 优雅退出机制
"""

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import List

# 添加当前目录到Python路径，以支持相对导入
sys.path.insert(0, str(Path(__file__).parent))

from core import TaskFactory, TaskGraph, TaskScheduler
from tasks.base import is_shutdown_requested, reset_shutdown_flag
from utils import check_version, get_assets_info, SCRIPT_VERSION, setup_signal_handlers


class NizimaFetcher:
    """Nizima下载器主控制器 v4.0

    基于任务图的全新架构，支持模块化任务管理和并发执行
    """

    def __init__(self, item_id: str, output_dir: str = "models/nizima"):
        """初始化下载器

        Args:
            item_id: 作品ID
            output_dir: 输出目录
        """
        self.item_id = str(item_id)
        self.output_dir = Path(output_dir)

    async def fetch(self) -> bool:
        """下载作品

        Returns:
            bool: 是否成功下载
        """
        print("🚀 开始下载 Nizima 作品: {}".format(self.item_id))
        print("=" * 60)

        # 重置关闭标志
        reset_shutdown_flag()

        # 检查版本，如果已是最新版本则跳过
        if check_version(self.item_id, str(self.output_dir)):
            return True

        try:
            # 1. 获取资源信息
            print("📋 获取资源信息...")
            assets_info, detail_data = await get_assets_info(self.item_id)

            # 如果没有preview模型，直接跳过
            if not assets_info.preview_live2d_zip:
                print("⚠️ 该作品没有Preview模型，直接跳过")
                return False

            # 2. 创建临时工作目录
            with tempfile.TemporaryDirectory(
                prefix=f"nizima_{self.item_id}_"
            ) as temp_dir_str:
                temp_dir = Path(temp_dir_str)
                print(f"📁 创建临时工作目录: {temp_dir}")

                # 3. 创建任务工厂和调度器
                factory = TaskFactory(self.item_id, self.output_dir, temp_dir)
                scheduler = TaskScheduler(max_concurrent=5)

                # 4. 构建任务图
                print("🏗️ 构建任务图...")
                try:
                    task_graph = await factory.create_task_graph(
                        assets_info, detail_data
                    )
                    print(f"📊 任务图构建完成，共 {len(task_graph.tasks)} 个任务")

                    # 显示任务图结构
                    print("📋 任务图结构:")
                    print(task_graph)

                except Exception as e:
                    print(f"❌ 构建任务图失败: {e}")
                    return False

                # 5. 执行任务图
                print("⚡ 开始执行任务图...")
                try:
                    success = await scheduler.execute_graph(task_graph)

                    if success:
                        print("✅ 所有任务执行完成")

                        # 6. 移动结果到最终位置
                        await self._finalize_output(temp_dir, task_graph)

                        return True
                    else:
                        print("❌ 任务执行失败")
                        return False

                except Exception as e:
                    print(f"❌ 执行任务图失败: {e}")
                    return False

        except Exception as e:
            print(f"❌ 下载失败: {e}")
            return False

    async def _finalize_output(self, temp_dir: Path, task_graph: TaskGraph):
        """完成输出处理

        Args:
            temp_dir: 临时目录
            task_graph: 任务图
        """
        # 查找重命名任务的结果
        rename_task = None
        for task in task_graph.tasks.values():
            if task.task_id.startswith(f"rename_dir_{self.item_id}"):
                rename_task = task
                break

        if rename_task and rename_task.completed and rename_task.result:
            final_dir = rename_task.result
            print(f"📁 最终输出目录: {final_dir}")
        else:
            # 如果没有重命名任务，直接移动到默认位置
            final_dir = self.output_dir / self.item_id
            final_dir.parent.mkdir(parents=True, exist_ok=True)

            if final_dir.exists():
                import shutil

                shutil.rmtree(final_dir)

            shutil.move(str(temp_dir), str(final_dir))
            print(f"📁 输出目录: {final_dir}")


async def fetch_multiple_items(
    item_ids: List[str], output_dir: str = "models/nizima", max_concurrent: int = 3
) -> None:
    """批量下载多个作品

    Args:
        item_ids: 作品ID列表
        output_dir: 输出目录
        max_concurrent: 最大并发数
    """
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


async def main():
    """主函数"""
    import argparse

    # 设置信号处理器
    setup_signal_handlers()

    parser = argparse.ArgumentParser(description="Nizima Live2D模型下载器 v4.0")
    parser.add_argument("item_ids", nargs="+", help="作品ID列表")
    parser.add_argument(
        "--output", "-o", default="../../models/nizima", help="输出目录"
    )
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

"""
权重动态调优模块 - 随机搜索 + 局部微调
目标: 找到让 Top10 避开命中率跑赢79.37%基线的最优权重配比

方法:
1. 随机搜索: 随机生成200组权重, 找到最好的几组
2. 局部微调: 在最优附近做步长0.01的迭代优化
3. 验证: 对比默认权重 vs 优化权重

核心思想: 权重不是主观给定的, 而是回测数据驱动的
"""

import random
from typing import Dict, List, Tuple
from config import ENGINE_WEIGHTS, TOP_N_LEVELS, BACKTEST_CONFIG, get_game_config, get_number_pool
from backtest.backtest_runner import BacktestRunner


class WeightOptimizer:
    """回测驱动的权重调优器"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.pool = get_number_pool(game_key)

        # 默认权重配置 (包含6引擎)
        self.default_weights = {
            "freq": 0.08,
            "bayesian": 0.22,
            "markov": 0.36,
            "joint": 0.34,
            "fft": 0.01,
            "monte_carlo": 0.00,
        }

        # 可调优的引擎列表 (包含MC)
        self.tunable_engines = ["freq", "bayesian", "markov", "joint", "fft", "monte_carlo"]

        # 回测窗口
        self.window = BACKTEST_CONFIG["window"]

        # 预加载所有数据
        from data.processor import DataProcessor
        self.processor = DataProcessor(self.game_key)
        self.all_records = self.processor.fetcher.get_all_draws()

    def _run_backtest_with_weights(self, weights: Dict[str, float]) -> Dict:
        """用指定权重跑100期回测, 返回结果"""
        from engines.engine_fusion import EngineFusion
        from math import comb

        K = len(self.pool)  # 39
        m = self.cfg["draw_count"]  # 5

        if len(self.all_records) < self.window + 50:
            return {"error": "数据不足"}

        test_records = self.all_records[-(self.window + 10):]

        # 创建fusion并设权重
        fusion = EngineFusion(self.game_key)
        fusion.weights = {eid: weights.get(eid, 0) for eid in fusion.engines}

        # 随机基线
        random_baselines = {}
        for level in TOP_N_LEVELS:
            n = level
            if K - n >= m:
                baseline = 1 - comb(K - n, m) / comb(K, m)
            else:
                baseline = 1.0
            random_baselines[level] = round(baseline, 4)

        avoid_hit_counts = {level: {"at_least_1": 0, "total": 0, "avg_count": 0}
                           for level in TOP_N_LEVELS}
        rebound_hit_counts = {level: {"at_least_1": 0, "total": 0, "avg_count": 0}
                             for level in TOP_N_LEVELS}

        for i in range(10, len(test_records)):
            train_data = test_records[:i]
            verify_record = test_records[i]
            verify_numbers = self.processor.extract_numbers_from_record(verify_record)
            verify_set = set(verify_numbers)

            avoid_ranking = fusion.get_avoid_ranking(train_data)
            rebound_ranking = fusion.get_rebound_ranking(train_data)

            for level in TOP_N_LEVELS:
                avoid_top = [n for n, _ in avoid_ranking[:level]]
                avoid_hit_count = sum(1 for n in avoid_top if n in verify_set)
                avoid_at_least_1 = avoid_hit_count >= 1
                avoid_hit_counts[level]["total"] += 1
                if avoid_at_least_1:
                    avoid_hit_counts[level]["at_least_1"] += 1
                avoid_hit_counts[level]["avg_count"] += avoid_hit_count

                rebound_top = [n for n, _, _ in rebound_ranking[:level]]
                rebound_hit_count = sum(1 for n in rebound_top if n in verify_set)
                rebound_at_least_1 = rebound_hit_count >= 1
                rebound_hit_counts[level]["total"] += 1
                if rebound_at_least_1:
                    rebound_hit_counts[level]["at_least_1"] += 1
                rebound_hit_counts[level]["avg_count"] += rebound_hit_count

        # 汇总
        avoid_stats = {}
        rebound_stats = {}
        for level in TOP_N_LEVELS:
            total = avoid_hit_counts[level]["total"]
            avoid_stats[level] = {
                "hit_rate": round(avoid_hit_counts[level]["at_least_1"] / total, 4) if total > 0 else 0,
                "avg_hit_count": round(avoid_hit_counts[level]["avg_count"] / total, 4) if total > 0 else 0,
                "random_baseline": random_baselines[level],
                "beat_baseline": (avoid_hit_counts[level]["at_least_1"] / total) > random_baselines[level] if total > 0 else False,
                "margin": round((avoid_hit_counts[level]["at_least_1"] / total - random_baselines[level]) * 100, 2) if total > 0 else 0,
            }
            total_r = rebound_hit_counts[level]["total"]
            rebound_stats[level] = {
                "hit_rate": round(rebound_hit_counts[level]["at_least_1"] / total_r, 4) if total_r > 0 else 0,
                "avg_hit_count": round(rebound_hit_counts[level]["avg_count"] / total_r, 4) if total_r > 0 else 0,
            }

        return {
            "weights": weights,
            "avoid_stats": avoid_stats,
            "rebound_stats": rebound_stats,
            "total_tested": avoid_hit_counts[2]["total"],
        }

    def _generate_random_weights(self) -> Dict[str, float]:
        """生成随机权重(总和=1, Dirichlet分布)"""
        engines = self.tunable_engines
        # 用Dirichlet分布生成随机权重, alpha=[1,1,1,1,1] → 均匀随机
        # 也可以用alpha=[3,3,2,1,2] → 偏向某些引擎
        alphas = [1.0] * len(engines)  # 均匀随机
        raw = [random.gammavariate(a, 1.0) for a in alphas]
        total = sum(raw)
        weights = {engines[i]: round(raw[i] / total, 4) for i in range(len(engines))}
        return weights

    def random_search(self, n_trials: int = 200, top_n_focus: int = 10) -> Dict:
        """
        随机搜索最优权重

        Parameters:
            n_trials: 随机试验次数(默认200)
            top_n_focus: 聚焦TopN级别做优化

        Returns: 最优权重组合及其回测结果
        """
        print(f"🎲 随机搜索: 试验次数={n_trials}, 聚焦Top{top_n_focus}命中率")
        print(f"   引擎: {self.tunable_engines}")

        best_result = None
        best_margin = -999
        best_weights = None
        top5_results = []  # 保存前5个最好的

        for trial in range(n_trials):
            weights = self._generate_random_weights()

            # 每5次试验, 也试试一些偏好性权重
            if trial % 10 == 0:
                # 偏向马尔可夫+联合(回测驱动最优方向)
                alphas_bias = [1.0, 2.0, 4.0, 4.0, 0.5, 1.0]  # freq,bayesian,markov,joint,fft,monte_carlo
                raw = [random.gammavariate(a, 1.0) for a in alphas_bias]
                total = sum(raw)
                weights = {self.tunable_engines[i]: round(raw[i] / total, 4)
                           for i in range(len(self.tunable_engines))}

            result = self._run_backtest_with_weights(weights)

            if "error" in result:
                continue

            margin = result["avoid_stats"].get(top_n_focus, {}).get("margin", -999)

            if margin > best_margin:
                best_margin = margin
                best_weights = weights
                best_result = result
                print(f"   🎯 试验 {trial+1}: margin={margin:+.2f}% 权重={weights}")

            # 保存top5
            top5_results.append((margin, weights, result))
            top5_results.sort(key=lambda x: x[0], reverse=True)
            top5_results = top5_results[:5]

            if trial % 50 == 0 and trial > 0:
                print(f"   进度 {trial}/{n_trials} | 当前最佳margin={best_margin:.2f}%")

        print(f"\n✅ 随机搜索完成: {n_trials}次试验")
        print(f"   🏆 最优权重: {best_weights}")
        print(f"   🏆 Top{top_n_focus} margin: {best_margin:+.2f}%")

        # 打印前5名
        print(f"\n   📊 Top5权重:")
        for i, (m, w, r) in enumerate(top5_results):
            print(f"   #{i+1}: margin={m:+.2f}% | {w}")

        return {
            "best_weights": best_weights,
            "best_result": best_result,
            "top5_results": top5_results,
            "tested_count": n_trials,
            "best_margin": best_margin,
            "focus_level": top_n_focus,
        }

    def local_search(self, base_weights: Dict[str, float], step: float = 0.02,
                     top_n_focus: int = 10, max_rounds: int = 8) -> Dict:
        """
        局部微调 - 在base_weights附近做迭代优化

        每轮: 对每个引擎尝试±step, 找到改善最大的调整, 应用之
        """
        print(f"🔍 局部微调: 步长={step}, 基础权重={base_weights}")

        best_weights = base_weights.copy()
        best_result = self._run_backtest_with_weights(best_weights)
        best_margin = best_result["avoid_stats"].get(top_n_focus, {}).get("margin", -999)

        tested_count = 0
        rounds = 0

        for round_idx in range(max_rounds):
            rounds += 1
            best_delta = None
            best_delta_margin = best_margin

            # 对每个引擎尝试±step
            engines = self.tunable_engines
            for eid in engines:
                for delta in [step, -step]:
                    new_weights = best_weights.copy()
                    new_weights[eid] = round(new_weights[eid] + delta, 4)

                    # 确保权重在[0, 0.7]范围内
                    if new_weights[eid] < 0 or new_weights[eid] > 0.7:
                        continue

                    # 归一化使总和=1
                    total = sum(new_weights.values())
                    if total <= 0:
                        continue
                    normalized = {e: round(v / total, 4) for e, v in new_weights.items()}

                    tested_count += 1
                    result = self._run_backtest_with_weights(normalized)

                    if "error" in result:
                        continue

                    margin = result["avoid_stats"].get(top_n_focus, {}).get("margin", -999)

                    if margin > best_delta_margin:
                        best_delta_margin = margin
                        best_delta = (eid, delta, normalized, result)

            if best_delta and best_delta_margin > best_margin:
                eid, delta, normalized, result = best_delta
                best_weights = normalized
                best_result = result
                best_margin = best_delta_margin
                print(f"   Round {rounds}: {eid} +{delta:.2f} → margin={best_margin:+.2f}%")
            else:
                print(f"   Round {rounds}: 无改善, 停止迭代")
                break

        print(f"\n✅ 局部微调完成: {tested_count}次测试, {rounds}轮迭代")
        print(f"   🏆 最终权重: {best_weights}")
        print(f"   🏆 Top{top_n_focus} margin: {best_margin:+.2f}%")

        return {
            "best_weights": best_weights,
            "best_result": best_result,
            "tested_count": tested_count,
            "best_margin": best_margin,
            "rounds": rounds,
        }

    def optimize(self, n_random: int = 200, local_step: float = 0.02,
                 top_n_focus: int = 10) -> Dict:
        """
        完整优化流程: 随机搜索 → 局部微调 → 对比默认权重
        """
        print("=" * 60)
        print("  🍡 权重动态调优 - 随机搜索 + 局部微调")
        print("=" * 60)

        # Phase 1: 随机搜索
        print("\n── Phase 1: 随机搜索 ──")
        random_result = self.random_search(n_random, top_n_focus)

        # Phase 2: 局部微调
        print("\n── Phase 2: 局部微调 ──")
        local_result = self.local_search(
            random_result["best_weights"], local_step, top_n_focus
        )

        # Phase 3: 对比默认权重
        print("\n── Phase 3: 对比默认权重 ──")
        default_result = self._run_backtest_with_weights(self.default_weights)

        final_weights = local_result["best_weights"]
        final_result = local_result["best_result"]

        # 输出对比
        print("\n" + "=" * 60)
        print("  🏆 优化结果对比")
        print("=" * 60)

        print(f"\n  默认权重: {self.default_weights}")
        for level in TOP_N_LEVELS:
            stats = default_result["avoid_stats"].get(level, {})
            margin = stats.get("margin", 0)
            beat = stats.get("beat_baseline", False)
            emoji = "✅" if beat else "❌"
            print(f"    {emoji} Top{level}: {stats.get('hit_rate', 0):.2%} | 基线={stats.get('random_baseline', 0):.2%} | margin={margin:+.2f}%")

        print(f"\n  优化权重: {final_weights}")
        for level in TOP_N_LEVELS:
            stats = final_result["avoid_stats"].get(level, {})
            margin = stats.get("margin", 0)
            beat = stats.get("beat_baseline", False)
            emoji = "✅" if beat else "❌"
            print(f"    {emoji} Top{level}: {stats.get('hit_rate', 0):.2%} | 基线={stats.get('random_baseline', 0):.2%} | margin={margin:+.2f}%")

        improvement = local_result["best_margin"] - default_result["avoid_stats"].get(top_n_focus, {}).get("margin", 0)
        print(f"\n  📈 优化提升: {improvement:+.2f}%")

        return {
            "optimized_weights": final_weights,
            "random_result": random_result,
            "local_result": local_result,
            "default_result": default_result,
            "final_margin": local_result["best_margin"],
            "improvement": improvement,
        }

    def format_optimization_report(self, result: Dict) -> str:
        """格式化优化报告"""
        lines = []
        lines.append("╔" + "═" * 58 + "╗")
        lines.append("║  🍡 权重动态调优报告 | 随机搜索+局部微调              ║")
        lines.append("╠" + "═" * 58 + "╣")
        lines.append("")

        # 默认权重 vs 优化权重
        default = result["default_result"]
        optimized = result.get("optimized_weights", {})
        final = result["local_result"]["best_result"]

        lines.append("  ── 📊 默认权重回测 ──")
        lines.append(f"  权重: {self.default_weights}")
        for level in TOP_N_LEVELS:
            stats = default["avoid_stats"].get(level, {})
            margin = stats.get("margin", 0)
            beat = stats.get("beat_baseline", False)
            emoji = "✅" if beat else "❌"
            lines.append(f"  {emoji} Top{level}: {stats.get('hit_rate', 0):.2%} | 基线={stats.get('random_baseline', 0):.2%} | margin={margin:+.2f}%")

        lines.append("")
        lines.append("  ── 🏆 优化权重回测 ──")
        lines.append(f"  权重: {optimized}")
        for level in TOP_N_LEVELS:
            stats = final["avoid_stats"].get(level, {})
            margin = stats.get("margin", 0)
            beat = stats.get("beat_baseline", False)
            emoji = "✅" if beat else "❌"
            lines.append(f"  {emoji} Top{level}: {stats.get('hit_rate', 0):.2%} | 基线={stats.get('random_baseline', 0):.2%} | margin={margin:+.2f}%")

        lines.append("")
        lines.append("  ── 📈 优化提升 ──")
        improvement = result.get("improvement", 0)
        lines.append(f"  Top10 margin提升: {improvement:+.2f}%")
        lines.append(f"  随机搜索: {result['random_result']['tested_count']} 次试验")
        lines.append(f"  局部微调: {result['local_result']['rounds']} 轮迭代")

        lines.append("")
        lines.append("  ── 💡 推荐操作 ──")
        final_margin = result.get("final_margin", 0)
        if final_margin > 0:
            lines.append(f"  ✅ 优化权重已跑赢基线 → 建议更新config.py")
        elif final_margin > -3:
            lines.append(f"  ⚠️ 优化权重接近基线 → 需扩充数据量")
        else:
            lines.append(f"  ❌ 优化权重仍输基线 → 引擎信号不足, 需更多引擎/数据")

        lines.append("╚" + "═" * 58 + "╝")
        return "\n".join(lines)


def run_optimize_cli(game_key: str = "fantasy5"):
    """CLI权重优化入口"""
    optimizer = WeightOptimizer(game_key)
    result = optimizer.optimize()
    report = optimizer.format_optimization_report(result)
    print(report)

    # 保存最优权重到config
    optimized = result["optimized_weights"]
    print(f"\n💡 推荐更新 config.py ENGINE_WEIGHTS:")
    print(f"   'freq': {optimized.get('freq', 0)},")
    print(f"   'bayesian': {optimized.get('bayesian', 0)},")
    print(f"   'markov': {optimized.get('markov', 0)},")
    print(f"   'joint': {optimized.get('joint', 0)},")
    print(f"   'fft': {optimized.get('fft', 0)}")

    return result

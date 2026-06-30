"""
回测验证模块 - 对E1+E2(和E1-E5)的避开命中率做100期回测
核心问题: 避开模式Top10的"命中率"是否能跑赢65.8%随机基线?

回测逻辑:
1. 选取最近100期作为验证期
2. 对每一期: 用该期之前的数据做预测 → 得到TopN号码列表
3. 检验: TopN中的号码在该期实际开奖中出现的个数
4. 避开命中率 = (TopN号码中至少1个出现在开奖中的比例) 
5. 对比随机基线: 随机选10个号, 至少1个出现的概率 ≈ 65.8%
   计算: P(at least 1 in Top10 appears) = 1 - C(34,5)/C(39,5) ≈ 0.658
"""

from typing import Dict, List, Tuple
from config import GAMES, TOP_N_LEVELS, BACKTEST_CONFIG, get_game_config, get_number_pool
from data.processor import DataProcessor
from engines.engine_fusion import EngineFusion


class BacktestRunner:
    """回测验证器"""

    def __init__(self, game_key: str = "fantasy5"):
        self.game_key = game_key
        self.cfg = get_game_config(game_key)
        self.pool = get_number_pool(game_key)
        self.processor = DataProcessor(game_key)
        self.K = len(self.pool)  # 39
        self.m = self.cfg["draw_count"]  # 5

    def run_backtest(self, window: int = 100, engines: str = "e1_e2") -> Dict:
        """
        运行回测

        Parameters:
            window: 回测窗口大小(最近N期)
            engines: "e1_e2" 仅E1+E2, "e1_e5" 全部5引擎

        Returns: 回测报告
        """
        all_records = self.processor.fetcher.get_all_draws()
        if len(all_records) < window + 50:
            print(f"⚠️ 数据量不足: 需要{window + 50}期, 实际{len(all_records)}期")
            return {}

        # 取最近window期作为验证期
        test_records = all_records[-(window + 10):]  # 多取10期做缓冲

        # 根据引擎选择初始化fusion
        fusion = EngineFusion(self.game_key)

        # 如果只用E1+E2, 修改权重
        if engines == "e1_e2":
            fusion.weights = {"freq": 0.45, "bayesian": 0.55, "markov": 0, "joint": 0, "fft": 0}

        results = {
            "engine_mode": engines,
            "window": window,
            "total_tested": 0,
            "avoid_stats": {},
            "rebound_stats": {},
            "per_period_details": [],
        }

        # ── 避开模式回测 ──
        avoid_hit_counts = {level: {"at_least_1": 0, "total": 0, "avg_count": 0}
                           for level in TOP_N_LEVELS}

        # ── 回补模式回测 ──
        rebound_hit_counts = {level: {"at_least_1": 0, "total": 0, "avg_count": 0}
                             for level in TOP_N_LEVELS}

        # 随机基线
        random_baselines = {}
        for level in TOP_N_LEVELS:
            # P(at least 1 in TopN appears in draw of 5 from 39)
            # = 1 - C(39-N, 5) / C(39, 5)
            from math import comb
            n = level
            if self.K - n >= self.m:
                baseline = 1 - comb(self.K - n, self.m) / comb(self.K, self.m)
            else:
                baseline = 1.0  # TopN超过号码池时必然命中
            random_baselines[level] = round(baseline, 4)

        # 逐期回测
        detail_list = []
        for i in range(10, len(test_records)):
            # 用i之前的数据做预测
            train_data = test_records[:i]
            # 验证期: test_records[i]
            verify_record = test_records[i]
            verify_numbers = self.processor.extract_numbers_from_record(verify_record)
            verify_set = set(verify_numbers)

            # 获取预测排名
            avoid_ranking = fusion.get_avoid_ranking(train_data)
            rebound_ranking = fusion.get_rebound_ranking(train_data)

            period_detail = {
                "draw_date": verify_record["draw_date"],
                "actual_numbers": verify_numbers,
            }

            for level in TOP_N_LEVELS:
                # ── 避开模式 ──
                avoid_top = [n for n, _ in avoid_ranking[:level]]
                avoid_hit_count = sum(1 for n in avoid_top if n in verify_set)
                avoid_at_least_1 = avoid_hit_count >= 1

                avoid_hit_counts[level]["total"] += 1
                if avoid_at_least_1:
                    avoid_hit_counts[level]["at_least_1"] += 1
                avoid_hit_counts[level]["avg_count"] += avoid_hit_count

                period_detail[f"avoid_top{level}"] = avoid_top
                period_detail[f"avoid_hit_top{level}"] = avoid_hit_count

                # ── 回补模式 ──
                rebound_top = [n for n, _, _ in rebound_ranking[:level]]
                rebound_hit_count = sum(1 for n in rebound_top if n in verify_set)
                rebound_at_least_1 = rebound_hit_count >= 1

                rebound_hit_counts[level]["total"] += 1
                if rebound_at_least_1:
                    rebound_hit_counts[level]["at_least_1"] += 1
                rebound_hit_counts[level]["avg_count"] += rebound_hit_count

                period_detail[f"rebound_top{level}"] = rebound_top
                period_detail[f"rebound_hit_top{level}"] = rebound_hit_count

            detail_list.append(period_detail)

        results["total_tested"] = len(detail_list)
        results["per_period_details"] = detail_list

        # 计算统计
        for level in TOP_N_LEVELS:
            total = avoid_hit_counts[level]["total"]
            results["avoid_stats"][level] = {
                "hit_rate": round(avoid_hit_counts[level]["at_least_1"] / total, 4) if total > 0 else 0,
                "avg_hit_count": round(avoid_hit_counts[level]["avg_count"] / total, 4) if total > 0 else 0,
                "random_baseline": random_baselines[level],
                "beat_baseline": (avoid_hit_counts[level]["at_least_1"] / total) > random_baselines[level] if total > 0 else False,
                "margin": round((avoid_hit_counts[level]["at_least_1"] / total - random_baselines[level]) * 100, 2) if total > 0 else 0,
            }

            total = rebound_hit_counts[level]["total"]
            results["rebound_stats"][level] = {
                "hit_rate": round(rebound_hit_counts[level]["at_least_1"] / total, 4) if total > 0 else 0,
                "avg_hit_count": round(rebound_hit_counts[level]["avg_count"] / total, 4) if total > 0 else 0,
            }

        return results

    def format_backtest_report(self, results: Dict) -> str:
        """格式化回测报告"""
        if not results:
            return "⚠️ 无回测数据"

        lines = []
        lines.append("╔" + "═" * 58 + "╗")
        lines.append(f"║  🍡 回测验证报告 | {self.cfg['name']} | {results['engine_mode']}            ║")
        lines.append(f"║  回测窗口: {results['window']}期 | 实际验证: {results['total_tested']}期             ║")
        lines.append("╠" + "═" * 58 + "╣")
        lines.append("")

        # ── 避开模式结果 ──
        lines.append("  ── 🔴 避开模式回测结果 ──")
        for level in TOP_N_LEVELS:
            stats = results["avoid_stats"].get(level, {})
            hit_rate = stats.get("hit_rate", 0)
            baseline = stats.get("random_baseline", 0)
            margin = stats.get("margin", 0)
            beat = stats.get("beat_baseline", False)
            avg = stats.get("avg_hit_count", 0)

            emoji = "✅" if beat else "❌"
            lines.append(f"  {emoji} Top{level}: 命中率={hit_rate:.2%} | 随机基线={baseline:.2%} | 超出={margin:+.2f}%")
            lines.append(f"     平均命中个数: {avg:.2f}/{level}")

        lines.append("")

        # ── 回补模式结果 ──
        lines.append("  ── 🟢 回补模式回测结果 ──")
        for level in TOP_N_LEVELS:
            stats = results["rebound_stats"].get(level, {})
            hit_rate = stats.get("hit_rate", 0)
            avg = stats.get("avg_hit_count", 0)
            lines.append(f"  🟢 Top{level}: 命中率={hit_rate:.2%} | 平均命中个数: {avg:.2f}/{level}")

        lines.append("")
        lines.append("  ── 📊 关键判断 ──")

        # 综合判断
        top10_stats = results["avoid_stats"].get(10, {})
        top10_beat = top10_stats.get("beat_baseline", False)
        top10_margin = top10_stats.get("margin", 0)

        if top10_beat and top10_margin >= 5:
            lines.append(f"  ✅ 避开Top10跑赢基线 +{top10_margin:.2f}% → 有统计参考价值")
        elif top10_beat:
            lines.append(f"  ⚠️ 避开Top10微跑赢基线 +{top10_margin:.2f}% → 信号较弱")
        else:
            lines.append(f"  ❌ 避开Top10未跑赢基线 {top10_margin:.2f}% → 需要优化引擎/权重")

        lines.append("╚" + "═" * 58 + "╝")

        return "\n".join(lines)


def run_backtest_cli(game_key: str = "fantasy5", window: int = 100, engines: str = "e1_e5"):
    """CLI回测入口"""
    runner = BacktestRunner(game_key)
    results = runner.run_backtest(window, engines)
    report = runner.format_backtest_report(results)
    print(report)
    return results

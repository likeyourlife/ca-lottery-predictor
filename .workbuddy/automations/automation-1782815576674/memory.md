# Automation Memory - 天天乐每日预测流水线

## 2026-07-01 首次执行

- 修复了 `daily_pipeline.py` 两个 bug：
  1. `BacktestRunner.run_backtest()` 不接受 records 参数 → 改为 `runner.run_backtest(window=100)`
  2. records 字段名 `date` → `draw_date`
- 流水线5步全部成功完成
- 数据量：682期
- 回测结果（100期）：Top2 ✅(+1.71%), Top4 ✅(+5.38%), Top10 ❌(-4.37%)
- 输出文件：data/fantasy5/daily_prediction.json, data/fantasy5/backtest_result.json

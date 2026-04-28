# experiments

Compatibility note: new public workflows should prefer `bidflow session run`. The modules in this directory remain supported so existing reports, scripts, and tests keep working during the BidFlow migration.

实验入口、批量运行、效用指标汇总、轮内动态投豆仿真、公式信息冲击对照实验和结果保存逻辑。

主入口：

```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id research_large_800x240x3_behavioral --agent behavioral --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/research_large --interaction-mode tool_based --time-points 3
```

可用 agent：

- `behavioral`：本地 persona 行为学生。
- `cass`：Competition-Adaptive Selfish Selector，纯规则 focal 或全量 agent。
- `openai`：OpenAI-compatible LLM agent。
- `mock`：测试用 mock agent。

`--focal-student-id` 目前支持 `openai` 和 `cass`。`--formula-prompt` 只支持 `openai`。

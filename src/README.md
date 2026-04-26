# src

Python 实验平台代码目录。

- `data_generation/`：合成数据生成、CSV 读取和基础校验。
- `auction_mechanism/`：单轮 all-pay 开奖、边界同分抽签、预算消耗。
- `student_agents/`：学生私有上下文、动态交互状态、输出校验。
- `llm_clients/`：mock LLM 和 OpenAI-compatible API 客户端。
- `experiments/`：单轮 MVP 实验调度入口。

当前可运行入口：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset smoke
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id smoke_mock --agent mock --experiment-group E0_llm_natural_baseline
python -m src.experiments.run_repeated_single_round_mvp --config configs/simple_model.yaml --run-prefix e0_mock --agent mock --experiment-group E0_llm_natural_baseline --n-repetitions 3
```

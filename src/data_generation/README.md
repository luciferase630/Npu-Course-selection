# data_generation

合成数据生成模块，包括学生、课程班、老师、培养方案、学生-课程班效用边表和竞争强度校准。

主入口仍是：

```powershell
python -m src.data_generation.generate_synthetic_mvp --scenario configs/generation/research_large_high.yaml
```

`generate_synthetic_mvp.py` 保留旧 `--preset` façade；新数据集优先通过 `configs/generation/*.yaml` 场景文件配置。场景格式见 `docs/generator_scenarios.md`。

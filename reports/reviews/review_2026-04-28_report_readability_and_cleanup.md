# 报告体系审阅与清理记录

> 日期：2026-04-28
> 目标：让项目对外阅读路径清晰，避免旧报告和新结论互相打架。

## 审阅结论

项目报告材料已经足够支撑公开阅读，但此前存在三个问题：

1. `reports/README.md` 仍指向 2026-04-27 的旧 CASS/LLM 结论，没有把 2026-04-28 的公式拟合、CASS 策略族和 BidFlow 平台化纳入主线。
2. `reports/interim/README.md` 和 `reports/final/README.md` 只是占位，不足以告诉读者先读哪几篇。
3. 根目录存在临时审计脚本和一篇过期的未跟踪 open-readiness 审阅稿，容易误导维护者。

## 本次修改

- 新增 `reports/final/report_2026-04-28_modeling_process.md`，作为当前主建模过程报告。
- 重写 `reports/README.md`，明确当前主线、补充结论、目录含义和 historical 阅读提醒。
- 重写 `reports/interim/README.md`，区分“当前仍建议阅读”和 historical。
- 重写 `reports/final/README.md`，给出 final 目录的实际入口。
- 更新根 `README.md` 的报告链接，把建模过程报告放在第一位。
- 删除未跟踪的 `tmp_audit_competitive.py`，避免临时脚本污染项目根目录。
- 删除未跟踪且已过期的 `reports/reviews/review_2026-04-27_project_status_and_open_readiness.md`。该稿中关于“还没有插件接口/沙盒平台”的判断已经被后续 BidFlow 平台化改动覆盖。

## 保留策略

没有删除已跟踪的 historical 报告。原因是这些文件记录了实验推进和结论修正过程；直接删除会降低可审计性。

改为：

- 在 `reports/README.md` 中声明“公开引用以 final 和 2026-04-28 主线报告为准”。
- 在 `reports/interim/README.md` 中把旧报告列为 historical。
- 在根 `README.md` 中只暴露当前主线报告和少量历史推进链接。

## 当前推荐阅读路径

1. `README.md`
2. `reports/final/report_2026-04-28_modeling_process.md`
3. `reports/interim/report_2026-04-28_crowding_boundary_formula_fit.md`
4. `reports/interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md`
5. `reports/interim/report_2026-04-28_cass_sensitivity_analysis.md`
6. `docs/reproducible_experiments.md`

## 可用性检查建议

每次文档/平台改动后至少运行：

```powershell
python -m compileall src bidflow
python -m unittest discover -s tests
python -m bidflow --help
python -m bidflow analyze crowding-boundary --quick
```

提交前继续检查：

- `.env*` 不入库。
- `data/synthetic/*` 不入库。
- `outputs/runs/*`、`outputs/tables/*` 不入库。
- 临时脚本不放在根目录。

# scripts

这里放可复现实验的 PowerShell 入口。脚本默认从仓库根目录运行，并调用 `python -m ...` 模块入口。

推荐使用分组目录：

- `generation/`：生成和审计合成数据。
- `experiments/`：运行 behavioral、CASS、LLM 等实验。

根目录下的旧脚本保留为兼容入口。

推荐顺序：

```powershell
.\scripts\run_smoke.ps1
.\scripts\generation\generate_research_large.ps1
.\scripts\experiments\run_research_large_behavioral.ps1
.\scripts\experiments\run_s048_cass_replay.ps1
.\scripts\run_s048_cass_online.ps1
```

如果要指定 Python 解释器：

```powershell
.\scripts\run_smoke.ps1 -Python .\.venv\Scripts\python.exe
```

生成数据和输出目录仍受 `.gitignore` 控制，不会默认入库。

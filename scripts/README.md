# scripts

这里放可复现实验的 PowerShell 入口。脚本默认从仓库根目录运行，并调用 `python -m ...` 模块入口。

推荐顺序：

```powershell
.\scripts\run_smoke.ps1
.\scripts\run_research_large_behavioral.ps1
.\scripts\run_s048_cass_replay.ps1
.\scripts\run_s048_cass_online.ps1
```

如果要指定 Python 解释器：

```powershell
.\scripts\run_smoke.ps1 -Python .\.venv\Scripts\python.exe
```

生成数据和输出目录仍受 `.gitignore` 控制，不会默认入库。

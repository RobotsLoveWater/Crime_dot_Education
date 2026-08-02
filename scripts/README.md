# Development scripts

## Resetting development instance state

`reset-instance.ps1` archives the current development accounts and classes, then
creates empty `user/` and `classes/` directories. It never removes or changes
`cache/`, `dataset.sav`, or `content/lessons/`.

From the repository root:

```powershell
.\scripts\reset-instance.ps1 -WhatIf
.\scripts\reset-instance.ps1 -Force
```

Archives are stored in `instance-archives/instance-YYYYMMDD-HHMMSS/` by default.
Each archive includes `user/`, `classes/`, and `manifest.json`; it can contain
password hashes, rosters, and student activity, so do not commit or share it.

For a future layout where runtime state is under `instance/`, specify it
explicitly (the state directory must contain `user/`, `classes/`, and `cache/`):

```powershell
.\scripts\reset-instance.ps1 -InstanceRoot .\instance -ArchiveRoot .\instance-archives -WhatIf
```

`-WhatIf` performs validation without changing files. The command prompts before
moving state; use `-Force` to suppress that prompt. `-Force` never overwrites an
existing archive.

Run the dependency-free test fixture with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\scripts\reset-instance.Tests.ps1
```

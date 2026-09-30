# Run guided cycles until >= 99.8% improvement vs measured baseline
param(
    [string]$FocusRoot = "C:\Users\Samer\dashboard_0602_174304"
)

& "$PSScriptRoot\run_until_85pct.ps1" -FocusRoot $FocusRoot -TargetPct 99.8 -MaxCycles 200

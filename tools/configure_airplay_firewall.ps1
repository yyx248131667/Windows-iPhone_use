#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ReceiverPath,
    [string]$InterfaceAlias,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$rulePrefix = 'Windows-iPhone-UxPlay'
$ruleNames = @("$rulePrefix-TCP", "$rulePrefix-UDP")

if ($Remove) {
    foreach ($ruleName in $ruleNames) {
        Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
    Write-Host 'AirPlay application rules removed.'
    exit 0
}

if (-not $ReceiverPath) {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $ReceiverPath = Join-Path $projectRoot '.runtime/airplay/msys64/ucrt64/bin/uxplay.exe'
}
$ReceiverPath = (Resolve-Path -LiteralPath $ReceiverPath).Path
if (-not $InterfaceAlias) {
    $network = Get-NetIPConfiguration | Where-Object {
        $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up'
    } | Select-Object -First 1
    if (-not $network) {
        throw 'No active network with an IPv4 gateway found. Specify -InterfaceAlias.'
    }
    $InterfaceAlias = $network.InterfaceAlias
}

# Scope access to this executable, the selected interface and local subnet.
# The local-only video bridge (7110) and WebUI (8000) are not opened.
foreach ($ruleName in $ruleNames) {
    Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}
$common = @{
    Direction = 'Inbound'
    Action = 'Allow'
    Enabled = 'True'
    Profile = @('Private', 'Public')
    Program = $ReceiverPath
    InterfaceAlias = $InterfaceAlias
    RemoteAddress = 'LocalSubnet'
    Group = 'Windows-iPhone AirPlay'
}
New-NetFirewallRule @common -Name "$rulePrefix-TCP" -DisplayName 'Windows-iPhone AirPlay TCP' -Protocol TCP -LocalPort '7100-7102' | Out-Null
New-NetFirewallRule @common -Name "$rulePrefix-UDP" -DisplayName 'Windows-iPhone AirPlay discovery and video' -Protocol UDP -LocalPort @('5353', '7100-7102') | Out-Null
Write-Host "AirPlay allowed on local subnet via $InterfaceAlias."
Write-Host 'Reopen Screen Mirroring on the iPhone and select Windows-iPhone.'

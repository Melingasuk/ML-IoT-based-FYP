$ErrorActionPreference = 'Stop'
$privateConfig = Join-Path $PSScriptRoot '../../../work/soilhealth-private/bridge.json'
if (-not (Test-Path -LiteralPath $privateConfig)) {
    throw 'The private cloud bridge configuration has not been set up on this computer.'
}
python (Join-Path $PSScriptRoot 'cloud_bridge.py') --config $privateConfig

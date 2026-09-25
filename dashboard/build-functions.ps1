$ErrorActionPreference = 'Stop'
$esbuild = Join-Path $PSScriptRoot '../../work/netlify-tools/node_modules/@esbuild/win32-x64/esbuild.exe'
Push-Location $PSScriptRoot
try {
    & $esbuild netlify/functions/api.mjs netlify/functions/login.mjs netlify/functions/ingest.mjs netlify/functions/receipt.mjs --bundle --platform=node --format=esm --target=node22 --out-extension:.js=.mjs --outdir=netlify/prebuilt
    if ($LASTEXITCODE -ne 0) { throw 'Function build failed' }
} finally { Pop-Location }

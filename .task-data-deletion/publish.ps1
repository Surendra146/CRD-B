$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'D:\web apps\React\CBD project'
function Check-Git { if ($LASTEXITCODE -ne 0) { throw 'Git command failed' } }
$staged = git diff --cached --name-only
Check-Git
if ($staged) { throw 'Existing staged changes require review before publishing' }
git add -- public/data-deletion/index.html src/Pages/DataDeletion.jsx src/routes/AppRoutes.jsx public/privacy-policy/index.html
Check-Git
$utf8 = New-Object System.Text.UTF8Encoding($false)
foreach ($name in @('render.yaml', 'nginx.conf')) {
  $lines = git show "HEAD:$name"
  Check-Git
  $content = ($lines -join "`n") + "`n"
  if ($name -eq 'render.yaml') {
    $content = $content.Replace('    routes:', "    routes:`n      - type: rewrite`n        source: /data-deletion`n        destination: /data-deletion/index.html`n      - type: rewrite`n        source: /data-deletion/`n        destination: /data-deletion/index.html")
  } else {
    $content = $content.Replace('  location / {', "  location = /data-deletion {`n    try_files /data-deletion/index.html =404;`n  }`n`n  location = /data-deletion/ {`n    try_files /data-deletion/index.html =404;`n  }`n`n  location / {")
  }
  $temporary = Join-Path 'D:\web apps\Python\CBD_Python\.task-data-deletion' $name
  [IO.File]::WriteAllText($temporary, $content, $utf8)
  $hash = git hash-object -w -- $temporary
  Check-Git
  git update-index --cacheinfo "100644,$hash,$name"
  Check-Git
}
git diff --cached --stat
git diff --cached --check
Check-Git
git commit -m 'Add public data deletion instructions page'
Check-Git
git push origin main
Check-Git

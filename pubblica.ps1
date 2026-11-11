# Pubblica su GitHub la Release della versione corrente, con zip e installer di pacchetto.ps1.
# Uso:  powershell -ExecutionPolicy Bypass -File pubblica.ps1 -Note note.md
#       (note.md: le novità; devono dire che il codice è scritto con l'intelligenza artificiale)
param([Parameter(Mandatory = $true)][string]$Note)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$version = (Select-String -Path Cargo.toml -Pattern '^version\s*=\s*"(.+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
$name = "PDFLayoutMeasure-$version"
$zip = Join-Path 'dist' "$name.zip"
if (-not (Test-Path $zip)) { throw "Manca ${zip}: esegui prima pacchetto.ps1" }
if (-not (Test-Path $Note)) { throw "File delle note non trovato: $Note" }
if ((Get-Content -Raw -Encoding UTF8 $Note) -notmatch 'intelligenza artificiale') {
    throw 'Le note devono dire che il codice è stato scritto con l''intelligenza artificiale'
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
$gh = if ($gh) { $gh.Source } else { 'C:\Program Files\GitHub CLI\gh.exe' }

# La Release punta al commit pubblicato: niente modifiche in sospeso
$dirty = git status --porcelain
if ($dirty) { throw 'Ci sono modifiche non salvate in git: fai prima commit e push' }

# Privacy: il commit deve essere già su GitHub (l'hook pre-push ha controllato codice, messaggi e
# autori) e note e file di testo del pacchetto non devono contenere parole vietate
git fetch --quiet origin
$head = git rev-parse HEAD
git merge-base --is-ancestor $head origin/main
if ($LASTEXITCODE -ne 0) { throw 'Il commit corrente non è su GitHub: fai prima il push' }
$list = Join-Path (git rev-parse --git-dir) 'info\parole-vietate.txt'
if (-not (Test-Path $list)) { throw "Manca ${list}: senza l'elenco delle parole vietate non si pubblica" }
$patterns = @(Get-Content -Encoding UTF8 $list | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
$folder = Join-Path 'dist' $name
$texts = @(Get-Item $Note) + @(Get-ChildItem -Recurse -File $folder -Include *.txt, *.md)
foreach ($file in $texts) {
    $content = Get-Content -Raw -Encoding UTF8 $file.FullName
    foreach ($pattern in $patterns) {
        if ($content -match $pattern) {
            throw "PUBBLICAZIONE BLOCCATA: $($file.Name) contiene un riferimento non anonimo ($($Matches[0]))"
        }
    }
}
Write-Host "Controllo privacy: note e $($texts.Count - 1) file di testo del pacchetto puliti"

$assets = @($zip)
$setup = Join-Path 'dist' "$name-setup.exe"
if (Test-Path $setup) { $assets += $setup } else { Write-Warning "Manca ${setup}: pubblico solo lo zip" }
& $gh release create "v$version" @assets --title "PDF Layout Measure $version" --notes-file $Note
if ($LASTEXITCODE -ne 0) { throw 'Pubblicazione non riuscita' }
Write-Host "Pubblicata: v$version"

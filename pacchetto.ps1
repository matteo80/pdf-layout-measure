# Prepara la cartella, lo zip e l'installer da distribuire:
#   dist\PDFLayoutMeasure-<versione>.zip  e  dist\PDFLayoutMeasure-<versione>-setup.exe
# Uso:  powershell -ExecutionPolicy Bypass -File pacchetto.ps1  [-SenzaCompilare]
param([switch]$SenzaCompilare)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not $SenzaCompilare) {
    cargo build --release
    if ($LASTEXITCODE -ne 0) { throw 'Compilazione non riuscita' }
}
$pdfium = 'third_party\pdfium\bin\pdfium.dll'
if (-not (Test-Path $pdfium)) { throw "Manca ${pdfium}: esegui prima scarica_pdfium.ps1" }

$version = (Select-String -Path Cargo.toml -Pattern '^version\s*=\s*"(.+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
$name = "PDFLayoutMeasure-$version"
$dir = Join-Path 'dist' $name
if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
New-Item -ItemType Directory -Force (Join-Path $dir 'licenses') | Out-Null

Copy-Item 'target\release\pdf_layout_measure.exe' $dir
Copy-Item $pdfium $dir
Copy-Item 'LICENSE' (Join-Path $dir 'LICENSE.txt')
Copy-Item 'licenses\*.txt' (Join-Path $dir 'licenses')

$readme = @"
PDF Layout Measure $version
===========================

Misure da layout in PDF: si calibra la scala su una distanza nota e si misurano
Delta X, Delta Y e distanza in mm.

Avvio: doppio clic su pdf_layout_measure.exe. Non serve installare niente: si può copiare
la cartella intera su un altro PC (Windows 10 o 11, 64 bit) o su una chiavetta.
pdfium.dll deve restare accanto all'eseguibile. In alternativa c'è l'installer
PDFLayoutMeasure-$version-setup.exe (menu Start, disinstallazione da «App installate»,
nessun permesso da amministratore).

Uso
- Apri PDF (o trascina il file sulla finestra, o passalo come argomento).
- Calibra scala: clicca due punti a distanza nota e scrivi la distanza reale in mm.
- Misura: clicca due punti; dopo il primo il risultato segue il mouse.
- Rotella: scorre; Shift + rotella: in orizzontale; Ctrl + rotella: zoom;
  trascinando con un tasto qualsiasi: sposta la vista; Esc: annulla la selezione.
- La scala vale per la pagina su cui è stata calibrata.

Autore: matteo80.
Il codice è stato scritto interamente con l'intelligenza artificiale (Claude, di Anthropic):
l'autore del progetto non ha scritto codice, ha definito le richieste e provato il programma.
Codice sorgente: https://github.com/matteo80/pdf-layout-measure

Licenze: LICENSE.txt (PDF Layout Measure, MIT) e la cartella licenses: librerie Rust incluse
nel programma (librerie-rust.txt) e pdfium con le librerie che include (pdfium-licenze.txt).
"@
# Fine riga di Windows, così il Blocco note lo mostra bene
Set-Content -Path (Join-Path $dir 'LEGGIMI.txt') -Value ($readme -replace "`r?`n", "`r`n") -Encoding UTF8 -NoNewline

$zip = Join-Path 'dist' "$name.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $dir -DestinationPath $zip
$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Pronto: $zip ($mb MB)"

# Installer (Inno Setup 6, se c'è)
$iscc = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc /Q "/DVersione=$version" 'installer\pdf_layout_measure.iss'
    if ($LASTEXITCODE -ne 0) { throw 'Installer non creato' }
    $setup = Join-Path 'dist' "$name-setup.exe"
    $mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
    Write-Host "Pronto: $setup ($mb MB)"
} else {
    Write-Warning 'Inno Setup 6 non trovato: niente installer (winget install JRSoftware.InnoSetup)'
}

<#
Windows' own OCR (Windows.Media.Ocr, Windows 10+): the words of each picture with their boxes, as one JSON line per
picture: {"path": …, "width": …, "height": …, "words": [{"t": text, "x": …, "y": …, "w": …, "h": …}, …]}.
Used by vic3tools.ocr; the language must be installed in Windows (en-US, ru are usual).
    powershell -NoProfile -ExecutionPolicy Bypass -File win_ocr.ps1 -Lang en-US a.png b.png
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Lang = "en-US",
    [Parameter(ValueFromRemainingArguments)] [string[]]$Paths
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
    Select-Object -First 1
function Await($op, [type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(); $task.Result }

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Lang))
if (-not $engine) { throw "no OCR language '$Lang' in Windows (installed: $(([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object LanguageTag) -join ', '))" }
foreach ($path in $Paths) {
    $full = (Resolve-Path $path).Path
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($full)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
        $words = foreach ($l in $res.Lines) {
            foreach ($w in $l.Words) {
                $r = $w.BoundingRect
                [ordered]@{ t = $w.Text; x = [int]$r.X; y = [int]$r.Y; w = [int]$r.Width; h = [int]$r.Height }
            }
        }
        [ordered]@{ path = $full; width = $bmp.PixelWidth; height = $bmp.PixelHeight; words = @($words) } |
            ConvertTo-Json -Compress -Depth 4
    } finally { $stream.Dispose() }
}

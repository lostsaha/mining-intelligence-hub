# 批量 .doc → .docx（Word COM，只读打开、另存为 12=wdFormatXMLDocument）
# 用法：powershell -File convert_docs.ps1 <manifest.tsv>   （每行：src<tab>dst）
$ErrorActionPreference = "Continue"
$lines = Get-Content -LiteralPath $args[0] -Encoding UTF8
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$ok = 0; $fail = 0
foreach ($line in $lines) {
    $parts = $line -split "`t"
    if ($parts.Count -lt 2) { continue }
    $src = $parts[0]; $dst = $parts[1]
    try {
        $doc = $word.Documents.Open($src, $false, $true)
        $doc.SaveAs2($dst, 12)
        $doc.Close($false)
        $ok++
        Write-Host "OK  $(Split-Path $src -Leaf)"
    } catch {
        $fail++
        Write-Host "FAIL $(Split-Path $src -Leaf) : $($_.Exception.Message)"
    }
}
$word.Quit()
Write-Host "done ok=$ok fail=$fail"

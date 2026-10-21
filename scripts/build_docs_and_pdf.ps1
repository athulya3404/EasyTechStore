$ErrorActionPreference = "Stop"

$htmlPath = "D:\EasyTechStore\docs\ethical_clearance_form_easytechstore.html"
$rootDocx = "D:\EasyTechStore\Ethical_Clearance_Form_EasyTechStore.docx"
$rootPdf  = "D:\EasyTechStore\Ethical_Clearance_Form_EasyTechStore.pdf"
$docsDocx = "D:\EasyTechStore\docs\Ethical_Clearance_Form_EasyTechStore.docx"
$docsPdf  = "D:\EasyTechStore\docs\Ethical_Clearance_Form_EasyTechStore.pdf"

# Clean prior outputs if they exist
foreach ($p in @($rootDocx, $rootPdf, $docsDocx, $docsPdf)) {
    if (Test-Path $p) { Remove-Item $p -Force }
}

Write-Output "Launching Microsoft Word COM engine..."
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
    Write-Output "Opening HTML template..."
    $doc = $word.Documents.Open($htmlPath)

    # Set page layout margins to 0.75 in (54 pt)
    $doc.PageSetup.TopMargin = 54
    $doc.PageSetup.BottomMargin = 54
    $doc.PageSetup.LeftMargin = 50
    $doc.PageSetup.RightMargin = 50

    Write-Output "Exporting Word DOCX to $rootDocx..."
    $doc.SaveAs2([ref]$rootDocx, [ref]16) # 16 = wdFormatXMLDocument (.docx)

    Write-Output "Exporting PDF to $rootPdf..."
    $doc.SaveAs2([ref]$rootPdf, [ref]17)  # 17 = wdFormatPDF (.pdf)

    $doc.Close([ref]0) # 0 = wdDoNotSaveChanges to source HTML

    # Copy to docs/ directory
    Copy-Item -Path $rootDocx -Destination $docsDocx -Force
    Copy-Item -Path $rootPdf  -Destination $docsPdf -Force

    Write-Output "SUCCESS: Generated both DOCX and PDF files successfully!"
}
catch {
    Write-Error "Conversion error: $_"
}
finally {
    $word.Quit([ref]0)
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

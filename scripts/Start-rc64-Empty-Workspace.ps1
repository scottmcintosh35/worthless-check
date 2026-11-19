# Packaging template: run build_empty_workspace_kit.py to insert verified artifact hashes.
[CmdletBinding()]
param([string]$WorkspaceFolder)
$ErrorActionPreference='Stop'
$local=[Environment]::GetFolderPath('LocalApplicationData')
$prefix='Check-Management-rc64-Empty-'
if($WorkspaceFolder){
    $profile=(Get-Item -LiteralPath $WorkspaceFolder -ErrorAction Stop).FullName.TrimEnd('\')
    if((Split-Path -Parent $profile) -ine $local -or (Split-Path -Leaf $profile) -notmatch ('^'+[regex]::Escape($prefix)+'[0-9a-f]{32}$')){throw 'Choose only an existing isolated empty-workspace profile created by this launcher.'}
    $evidence=Get-Content -LiteralPath (Join-Path $profile 'empty-workspace.json') -Raw|ConvertFrom-Json
    if($evidence.Build -ne '1.0.0-rc64' -or $evidence.Source -ne 'VERIFIED_EMPTY_BASELINE'){throw 'Workspace identity mismatch.'}
}else{
    $baseline=Join-Path $PSScriptRoot 'Empty-rc64.sqlite'
    $setup=Join-Path $PSScriptRoot 'Check-Management-Setup-rc64.exe'
    if((Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash -ine '__INSTALLER_SHA256__'){throw 'rc64 installer hash mismatch.'}
    foreach($suffix in @('-wal','-shm','-journal')){if(Test-Path -LiteralPath ($baseline+$suffix)){throw 'Empty baseline has an unexpected journal/sidecar.'}}
    $source=[IO.File]::Open($baseline,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try{
        $before=(Get-FileHash -LiteralPath $baseline -Algorithm SHA256).Hash
        if($before -ine '__EMPTY_SHA256__'){throw 'Empty baseline hash mismatch. Do not use a previously opened or modified baseline.'}
        $profile=Join-Path $local ($prefix+[guid]::NewGuid().ToString('N'))
        $dataFolder=Join-Path $profile 'Data'
        New-Item -ItemType Directory -Path $dataFolder|Out-Null
        $data=Join-Path $dataFolder 'wc.sqlite'
        $dest=[IO.File]::Open($data,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$source.CopyTo($dest);$dest.Flush()}finally{$dest.Dispose()}
        $copied=(Get-FileHash -LiteralPath $data -Algorithm SHA256).Hash
        $after=(Get-FileHash -LiteralPath $baseline -Algorithm SHA256).Hash
        if($copied -ine $before -or $after -ine $before){throw 'Empty database copy verification failed.'}
    }finally{$source.Dispose()}
    $appFolder=Join-Path $profile 'App'
    $extract=Start-Process -FilePath $setup -ArgumentList @('/EXTRACTONLY=1','/CURRENTUSER','/VERYSILENT','/NOCLOSEAPPLICATIONS','/NORESTART',('/DIR="'+$appFolder+'"')) -PassThru -Wait -WindowStyle Hidden
    if($extract.ExitCode -ne 0){throw 'Extract-only application preparation failed.'}
    $exe=Join-Path $appFolder 'PikeCountyWC.exe'
    $evidence=[pscustomobject]@{Build='1.0.0-rc64';Source='VERIFIED_EMPTY_BASELINE';Mode='test';InitialDatabaseSHA256=$copied;InitialUsers=0;InitialCases=0;InitialPayments=0;InitialImportedRecords=0;ExecutableSHA256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash;CreatedAt=(Get-Date).ToString('o');ExistingData='NOT READ OR MODIFIED';PendingTroyReceiptPairs='PENDING in existing databases; not copied or altered'}
    $evidence|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $profile 'empty-workspace.json') -Encoding UTF8
}
$appFolder=Join-Path $profile 'App'
$exe=Join-Path $appFolder 'PikeCountyWC.exe'
$data=Join-Path $profile 'Data\wc.sqlite'
if(-not (Test-Path -LiteralPath $data -PathType Leaf)){throw 'Workspace database is missing.'}
if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ine $evidence.ExecutableSHA256){throw 'Workspace executable changed since extraction.'}
Write-Host "EMPTY rc64 WORKSPACE: $profile"
Write-Host "DATABASE: $data"
Write-Host 'For a new workspace, first Administrator setup is EXPECTED. Create your own login. Leave fictional sample cases UNCHECKED.'
Write-Host 'This is an isolated TEST workspace, not the live server database or an approved production activation.'
Write-Host "REOPEN THIS SAME WORKSPACE: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -WorkspaceFolder `"$profile`""
Write-Host 'Existing databases/backups and pending Troy receipt pairs are unchanged.'
$start=New-Object Diagnostics.ProcessStartInfo
$start.FileName=$exe
$start.WorkingDirectory=$appFolder
$start.Arguments='--data "'+$data+'"'
$start.UseShellExecute=$false
$start.EnvironmentVariables['PROGRAMDATA']=$profile
[Diagnostics.Process]::Start($start)|Out-Null

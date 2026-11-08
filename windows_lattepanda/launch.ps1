# Een proces dat de SSH-sessie moet overleven. Start-Process erft het job-object van sshd en
# wordt mee afgebroken zodra de verbinding sluit; een proces dat via WMI wordt aangemaakt valt
# buiten die boom en blijft draaien.
param([string]$Script)
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "powershell -ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File $Script"
}
Write-Output "ReturnValue=$($r.ReturnValue)  ProcessId=$($r.ProcessId)"

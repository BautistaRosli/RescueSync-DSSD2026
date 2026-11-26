#Requires -Version 5.1
<#
.SYNOPSIS
    Mantiene el puente hacia el microservicio de prioridad en Kubernetes.

.DESCRIPTION
    Lanza `kubectl port-forward` contra el Service NodePort de prioridad y lo
    mantiene vivo durante N horas (24 por defecto). Si kubectl termina de forma
    inesperada, lo reinicia automáticamente.

    En Windows el NodePort de Docker Desktop no se publica en localhost, por eso
    el backend local consume el servicio a través de este puente.

.PARAMETER Hours
    Duración total del puente en horas. Por defecto 24.

.PARAMETER Foreground
    Ejecuta el bucle en esta terminal en lugar de lanzarlo en segundo plano.

.PARAMETER Stop
    Detiene el puente en ejecución.

.PARAMETER Status
    Informa si el puente está activo y si el puerto responde.

.EXAMPLE
    .\scripts\port-forward-prioridad.ps1
    Lanza el puente en segundo plano durante 24 horas.

.EXAMPLE
    .\scripts\port-forward-prioridad.ps1 -Hours 72
    Lanza el puente durante 72 horas.

.EXAMPLE
    .\scripts\port-forward-prioridad.ps1 -Stop
    Detiene el puente.
#>
[CmdletBinding()]
param(
    [int]$Hours = 24,
    [string]$Namespace = 'rescuesync',
    [string]$Service = 'rescuesync-prioridad-svc',
    [int]$LocalPort = 30080,
    [int]$RemotePort = 80,
    [int]$RestartDelaySeconds = 5,
    [switch]$Foreground,
    [switch]$Stop,
    [switch]$Status,
    [Parameter(DontShow)]
    [switch]$Worker
)

$ErrorActionPreference = 'Stop'

$stateDir = Join-Path $env:TEMP 'rescuesync-prioridad'
$pidFile = Join-Path $stateDir 'port-forward.pid'
$logFile = Join-Path $stateDir 'port-forward.log'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function Get-BridgeProcess {
    if (-not (Test-Path $pidFile)) { return $null }
    $guardado = (Get-Content $pidFile -Raw).Trim()
    if (-not $guardado) { return $null }
    return Get-Process -Id ([int]$guardado) -ErrorAction SilentlyContinue
}

function Test-Puerto {
    $conexion = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    return [bool]$conexion
}

if ($Stop) {
    $proceso = Get-BridgeProcess
    if ($proceso) {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proceso.Id)" -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $proceso.Id -Force -ErrorAction SilentlyContinue
        "Puente detenido (PID $($proceso.Id))."
    }
    else {
        "No hay ningún puente en ejecución."
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    return
}

if ($Status) {
    $proceso = Get-BridgeProcess
    $activo = $proceso -and (Test-Puerto)
    if ($activo) {
        "Puente activo (PID $($proceso.Id)), puerto $LocalPort escuchando."
        "Log: $logFile"
    }
    elseif (Test-Puerto) {
        "El puerto $LocalPort está ocupado por otro proceso."
    }
    else {
        "Puente inactivo."
    }
    return
}

if (-not $Worker -and -not $Foreground) {
    $existente = Get-BridgeProcess
    if ($existente) {
        "Ya hay un puente activo (PID $($existente.Id)). Usá -Stop para reiniciarlo."
        return
    }

    $argumentos = @(
        '-NoProfile'
        '-ExecutionPolicy', 'Bypass'
        '-File', "`"$PSCommandPath`""
        '-Worker'
        '-Hours', $Hours
        '-Namespace', $Namespace
        '-Service', $Service
        '-LocalPort', $LocalPort
        '-RemotePort', $RemotePort
        '-RestartDelaySeconds', $RestartDelaySeconds
    )

    $inicio = Start-Process -FilePath 'powershell.exe' -ArgumentList $argumentos -WindowStyle Hidden -PassThru
    Set-Content -Path $pidFile -Value $inicio.Id
    "Puente lanzado en segundo plano (PID $($inicio.Id)) durante $Hours h."
    "Log: $logFile"
    "Para detenerlo: .\scripts\port-forward-prioridad.ps1 -Stop"
    return
}

# Modo worker: bucle con plazo y auto-reinicio.
$limite = (Get-Date).AddHours($Hours)
"[$(Get-Date -Format o)] inicio del puente; límite $($limite.ToString('o'))" |
    Add-Content -Path $logFile

while ((Get-Date) -lt $limite) {
    "[$(Get-Date -Format o)] kubectl port-forward $LocalPort -> $RemotePort ($Namespace/$Service)" |
        Add-Content -Path $logFile

    & kubectl port-forward --address 0.0.0.0 -n $Namespace "svc/$Service" "${LocalPort}:${RemotePort}" *>> $logFile

    if ((Get-Date) -lt $limite) {
        "[$(Get-Date -Format o)] el puente terminó; reintento en $RestartDelaySeconds s" |
            Add-Content -Path $logFile
        Start-Sleep -Seconds $RestartDelaySeconds
    }
}

"[$(Get-Date -Format o)] fin del puente por plazo cumplido" | Add-Content -Path $logFile

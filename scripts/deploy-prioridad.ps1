#Requires -Version 5.1
<#
.SYNOPSIS
    Despliega el microservicio de prioridad y deja el puente local activo 24 h.

.DESCRIPTION
    Aplica los manifiestos de `k8s/`, espera el rollout del Deployment y luego
    lanza `kubectl port-forward` desacoplado durante N horas (24 por defecto).
    Es el punto de entrada recomendado para el deploy en Docker Desktop Windows.

.PARAMETER Hours
    Duración del puente en horas. Por defecto 24.

.PARAMETER SkipApply
    No reaplica los manifiestos; solo levanta o verifica el puente.

.EXAMPLE
    .\scripts\deploy-prioridad.ps1

.EXAMPLE
    .\scripts\deploy-prioridad.ps1 -Hours 72
#>
[CmdletBinding()]
param(
    [int]$Hours = 24,
    [switch]$SkipApply
)

$ErrorActionPreference = 'Stop'

$raiz = Split-Path -Parent $PSScriptRoot
$puente = Join-Path $PSScriptRoot 'port-forward-prioridad.ps1'

if (-not $SkipApply) {
    "Aplicando manifiestos de k8s/..."
    & kubectl apply -f (Join-Path $raiz 'k8s')
    if ($LASTEXITCODE -ne 0) { throw "kubectl apply falló con código $LASTEXITCODE." }

    "Esperando el rollout de rescuesync-prioridad..."
    & kubectl rollout status deployment/rescuesync-prioridad -n rescuesync --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "El rollout no terminó correctamente." }
}

& $puente -Hours $Hours
& $puente -Status

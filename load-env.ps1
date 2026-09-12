$envFile = ".env.example"

if (-not (Test-Path $envFile)) {
    throw "Missing $envFile file in project root."
}

foreach ($rawLine in Get-Content $envFile) {
    $line = $rawLine.Trim()

    if (-not $line -or $line.StartsWith("#")) {
        continue
    }

    $nameAndValue = $line.Split("=", 2)
    if ($nameAndValue.Count -ne 2) {
        continue
    }

    $name = $nameAndValue[0].Trim()
    $value = $nameAndValue[1].Trim().Trim("'").Trim('"')
    [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
}

# For direct local run outside Docker network.
if ($env:RABBITMQ_HOST -eq "rabbitmq") {
    $env:RABBITMQ_HOST = "localhost"
}

Write-Host "Loaded environment variables from $envFile"

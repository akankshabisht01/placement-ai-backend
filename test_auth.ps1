# Test Email/Username Authentication
Write-Host "Testing Email/Username Authentication System" -ForegroundColor Cyan
Write-Host "=" * 50

# Test 1: Check user by username
Write-Host "`nTest 1: User check with username 'ayush'" -ForegroundColor Yellow
try {
    $body = @{
        emailOrUsername = "ayush"
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/check-user" -Method Post -ContentType "application/json" -Body $body
    
    Write-Host "Result:" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 3
    
    if ($response.success -and $response.exists) {
        Write-Host "✅ Username lookup successful!" -ForegroundColor Green
    } else {
        Write-Host "❌ Username lookup failed" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 2: Check user by email
Write-Host "`nTest 2: User check with email 'ayushbahuguna23@gmail.com'" -ForegroundColor Yellow
try {
    $body = @{
        emailOrUsername = "ayushbahuguna23@gmail.com"
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/check-user" -Method Post -ContentType "application/json" -Body $body
    
    Write-Host "Result:" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 3
    
    if ($response.success -and $response.exists) {
        Write-Host "✅ Email lookup successful!" -ForegroundColor Green
    } else {
        Write-Host "❌ Email lookup failed" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 3: Check non-existent user
Write-Host "`nTest 3: Invalid user check with 'nonexistentuser'" -ForegroundColor Yellow
try {
    $body = @{
        emailOrUsername = "nonexistentuser"
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/check-user" -Method Post -ContentType "application/json" -Body $body
    
    Write-Host "Result:" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 3
    
    if ($response.success -and -not $response.exists) {
        Write-Host "✅ Invalid user correctly rejected!" -ForegroundColor Green
    } else {
        Write-Host "❌ Invalid user was not properly handled" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n" + "=" * 50
Write-Host "Tests completed!" -ForegroundColor Cyan
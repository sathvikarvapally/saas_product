param([string]$BaseUrl = 'http://127.0.0.1:8000')

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')

function Invoke-SubLedger {
    param([string]$Method, [string]$Path, [object]$Body)
    $requestParameters = @{ Method = $Method; Uri = "$BaseUrl$Path" }
    if ($null -ne $Body) {
        $requestParameters.ContentType = 'application/json'
        $requestParameters.Body = ConvertTo-Json -InputObject $Body -Depth 10
    }
    Invoke-RestMethod @requestParameters
}

function Assert-Result {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$runId = [guid]::NewGuid().ToString('N')
$plan = Invoke-SubLedger POST '/plans' @{
    name = 'Walkthrough Starter'; description = 'End-to-end demonstration'
    price = '499.00'; currency = 'INR'; billing_cycle = 'monthly'; status = 'active'
}
$customer = Invoke-SubLedger POST '/customers' @{
    name = 'Demo Customer'; email = "demo-$runId@example.com"; company_name = 'Demo Company'
}
$subscription = Invoke-SubLedger POST '/subscriptions' @{
    customer_id = $customer.id; plan_id = $plan.id
}
$invoice = Invoke-SubLedger POST '/invoices/generate' @{ subscription_id = $subscription.id }
Assert-Result ($invoice.status -eq 'issued') 'Invoice must start issued'

$partial = Invoke-SubLedger POST '/payments/record' @{
    invoice_id = $invoice.id; amount = '200.00'; currency = 'INR'
    status = 'success'; provider_reference = "$runId-partial"
}
Assert-Result ($partial.invoice.status -eq 'partially_paid') 'Partial payment must change status'
Assert-Result ([decimal]$partial.invoice.amount_paid -eq 200) 'Partial payment total is incorrect'

$failed = Invoke-SubLedger POST '/payments/record' @{
    invoice_id = $invoice.id; amount = '299.00'; currency = 'INR'
    status = 'failed'; provider_reference = "$runId-failed"; failure_reason = 'Demo decline'
}
Assert-Result ([decimal]$failed.invoice.amount_paid -eq 200) 'Failed attempt changed the balance'

$settled = Invoke-SubLedger POST '/payments/record' @{
    invoice_id = $invoice.id; amount = '299.00'; currency = 'INR'
    status = 'success'; provider_reference = "$runId-final"
}
Assert-Result ($settled.invoice.status -eq 'paid') 'Invoice must be paid'
Assert-Result ([decimal]$settled.invoice.amount_paid -eq 499) 'Final total is incorrect'
$ledger = Invoke-SubLedger GET "/customers/$($customer.id)/ledger"
Assert-Result ($ledger.Count -eq 4) 'Expected invoice, success, failure, and success ledger events'
$cancelled = Invoke-SubLedger PATCH "/subscriptions/$($subscription.id)/cancel"
Assert-Result ($cancelled.status -eq 'cancelled') 'Subscription cancellation failed'

[pscustomobject]@{
    Result = 'PASS'; PlanId = $plan.id; CustomerId = $customer.id
    SubscriptionId = $subscription.id; InvoiceId = $invoice.id
    InvoiceStatus = $settled.invoice.status; AmountPaid = $settled.invoice.amount_paid
    PaymentAttempts = 3; LedgerEvents = $ledger.Count; SubscriptionStatus = $cancelled.status
} | Format-List

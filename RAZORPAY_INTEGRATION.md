# Razorpay Payment Integration

## Setup

1. **Install Razorpay SDK** (already done):
   ```bash
   pip install razorpay
   ```

2. **Configure Environment Variables** in `.env`:
   ```env
   RAZORPAY_KEY_ID=your_razorpay_key_id
   RAZORPAY_KEY_SECRET=your_razorpay_key_secret
   ```

   Get your keys from: https://dashboard.razorpay.com/app/keys

## API Endpoints

### 1. Create Payment Order
**POST** `/api/payment/create-order`

Creates a Razorpay order for payment.

**Request Body:**
```json
{
  "amount": 50000,
  "currency": "INR",
  "receipt": "receipt#1",
  "notes": {
    "mobile": "+919876543210",
    "name": "John Doe",
    "purpose": "Premium Subscription"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "order_id": "order_xxxxxxxxxxxxx",
    "amount": 50000,
    "currency": "INR",
    "key_id": "rzp_test_xxxxx"
  }
}
```

### 2. Verify Payment
**POST** `/api/payment/verify`

Verifies payment signature after successful payment.

**Request Body:**
```json
{
  "razorpay_order_id": "order_xxxxxxxxxxxxx",
  "razorpay_payment_id": "pay_xxxxxxxxxxxxx",
  "razorpay_signature": "signature_xxxxxxxxxxxxx",
  "mobile": "+919876543210"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Payment verified successfully",
  "data": {
    "order_id": "order_xxxxxxxxxxxxx",
    "payment_id": "pay_xxxxxxxxxxxxx",
    "status": "success"
  }
}
```

### 3. Get Payment Status
**GET** `/api/payment/status/<order_id>`

Get payment status from database.

**Response:**
```json
{
  "success": true,
  "data": {
    "order_id": "order_xxxxxxxxxxxxx",
    "payment_id": "pay_xxxxxxxxxxxxx",
    "amount": 50000,
    "currency": "INR",
    "status": "success",
    "created_at": "2025-12-09T10:30:00",
    "verified_at": "2025-12-09T10:35:00"
  }
}
```

### 4. Get User Payments
**GET** `/api/payment/user-payments/<mobile>`

Get all payments for a specific user.

**Response:**
```json
{
  "success": true,
  "data": {
    "mobile": "919876543210",
    "payments": [
      {
        "order_id": "order_xxxxxxxxxxxxx",
        "payment_id": "pay_xxxxxxxxxxxxx",
        "amount": 50000,
        "currency": "INR",
        "status": "success",
        "created_at": "2025-12-09T10:30:00"
      }
    ],
    "total_payments": 1
  }
}
```

## Frontend Integration Example

```javascript
// 1. Create Order
const createOrder = async (amount, notes) => {
  const response = await fetch('http://localhost:5000/api/payment/create-order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      amount: amount * 100, // Convert rupees to paise
      currency: 'INR',
      receipt: `receipt_${Date.now()}`,
      notes: notes
    })
  });
  
  const data = await response.json();
  return data.data;
};

// 2. Open Razorpay Checkout
const initiatePayment = async (amount, userInfo) => {
  try {
    // Create order
    const orderData = await createOrder(amount, {
      mobile: userInfo.mobile,
      name: userInfo.name,
      purpose: 'Premium Subscription'
    });
    
    // Configure Razorpay options
    const options = {
      key: orderData.key_id,
      amount: orderData.amount,
      currency: orderData.currency,
      name: 'Placement AI',
      description: 'Premium Subscription',
      order_id: orderData.order_id,
      handler: async function (response) {
        // Payment successful - verify signature
        await verifyPayment(response, userInfo.mobile);
      },
      prefill: {
        name: userInfo.name,
        email: userInfo.email,
        contact: userInfo.mobile
      },
      theme: {
        color: '#3399cc'
      }
    };
    
    const razorpay = new window.Razorpay(options);
    razorpay.open();
    
  } catch (error) {
    console.error('Payment initiation failed:', error);
  }
};

// 3. Verify Payment
const verifyPayment = async (razorpayResponse, mobile) => {
  const response = await fetch('http://localhost:5000/api/payment/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      razorpay_order_id: razorpayResponse.razorpay_order_id,
      razorpay_payment_id: razorpayResponse.razorpay_payment_id,
      razorpay_signature: razorpayResponse.razorpay_signature,
      mobile: mobile
    })
  });
  
  const data = await response.json();
  
  if (data.success) {
    console.log('Payment verified successfully!');
    // Update UI, show success message, activate premium features
  } else {
    console.error('Payment verification failed');
  }
};

// Usage
const handlePremiumPurchase = () => {
  const userInfo = {
    name: 'John Doe',
    email: 'john@example.com',
    mobile: '+919876543210'
  };
  
  initiatePayment(499, userInfo); // ₹499
};
```

## HTML Script Tag

Add this script to your HTML before using Razorpay:

```html
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
```

## Database Schema

Payments are stored in the `payments` collection:

```javascript
{
  "_id": ObjectId("..."),
  "order_id": "order_xxxxxxxxxxxxx",
  "payment_id": "pay_xxxxxxxxxxxxx",
  "amount": 50000,
  "currency": "INR",
  "receipt": "receipt#1",
  "status": "success",  // created, success, failed
  "signature": "signature_xxxxxxxxxxxxx",
  "mobile": "919876543210",
  "notes": {
    "name": "John Doe",
    "purpose": "Premium Subscription"
  },
  "created_at": ISODate("2025-12-09T10:30:00Z"),
  "verified_at": ISODate("2025-12-09T10:35:00Z"),
  "updated_at": ISODate("2025-12-09T10:35:00Z")
}
```

## Testing

1. **Test Mode**: Use test keys from Razorpay dashboard
2. **Test Cards**: https://razorpay.com/docs/payments/payments/test-card-details/

Example test card:
- Card Number: 4111 1111 1111 1111
- Expiry: Any future date
- CVV: Any 3 digits

## Production Checklist

- [ ] Replace test keys with live keys in `.env`
- [ ] Enable webhook in Razorpay dashboard (optional)
- [x] Set up proper error logging ✅
- [x] Add payment failure handling ✅
- [x] Implement refund logic if needed
- [x] Add transaction receipts/invoices ✅
- [ ] Test with real bank accounts
- [x] Add payment analytics endpoint ✅
- [x] Track payment attempts in database ✅

## New Endpoints

### 5. Handle Payment Failure
**POST** `/api/payment/failure`

Logs payment failure details for analytics and debugging.

**Request Body:**
```json
{
  "order_id": "order_xxxxxxxxxxxxx",
  "error": {
    "code": "BAD_REQUEST_ERROR",
    "description": "Payment failed",
    "reason": "payment_failed",
    "step": "payment_authentication",
    "source": "customer"
  },
  "mobile": "+919876543210"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Payment failure logged"
}
```

### 6. Generate Receipt/Invoice
**GET** `/api/payment/receipt/<order_id>`

Generates detailed payment receipt with GST breakdown.

**Response:**
```json
{
  "success": true,
  "data": {
    "receipt_number": "RCP-order_xxxxx",
    "invoice_number": "INV-20251209-xxxxx",
    "date": "09 December 2025",
    "time": "10:30 AM",
    "customer": {
      "name": "John Doe",
      "mobile": "919876543210",
      "email": "john@example.com"
    },
    "payment": {
      "order_id": "order_xxxxxxxxxxxxx",
      "payment_id": "pay_xxxxxxxxxxxxx",
      "method": "Razorpay",
      "status": "PAID"
    },
    "items": [
      {
        "description": "Premium Plan Subscription",
        "quantity": 1,
        "unit_price": 423.73,
        "amount": 423.73
      }
    ],
    "amounts": {
      "subtotal": 423.73,
      "gst": 76.27,
      "gst_rate": "18%",
      "total": 500.00,
      "currency": "INR"
    },
    "company": {
      "name": "Placement AI",
      "address": "India",
      "email": "support@placementai.com",
      "website": "www.placementai.com",
      "gstin": "XXXXXXXXXXXXXXX"
    },
    "terms": [
      "This is a computer-generated receipt.",
      "No signature required.",
      "For queries, contact support@placementai.com"
    ]
  }
}
```

### 7. Payment Analytics
**GET** `/api/payment/analytics?days=30`

Get payment statistics and success rates (admin endpoint).

**Query Parameters:**
- `days` (optional): Number of days to analyze (default: 30)

**Response:**
```json
{
  "success": true,
  "data": {
    "period_days": 30,
    "start_date": "2025-11-09T10:00:00",
    "end_date": "2025-12-09T10:00:00",
    "summary": {
      "success": {
        "count": 45,
        "total_amount": 22500.00,
        "currency": "INR"
      },
      "failed": {
        "count": 5,
        "total_amount": 2500.00,
        "currency": "INR"
      },
      "created": {
        "count": 2,
        "total_amount": 1000.00,
        "currency": "INR"
      }
    },
    "success_rate": 90.0
  }
}
```

## Enhanced Features

### Error Logging
All payment operations now include comprehensive error logging:
- ✅ Detailed console output with timestamps
- ✅ Error categorization (critical, warning, info)
- ✅ Stack traces for debugging
- ✅ Formatted log sections for easy reading

### Payment Failure Tracking
- ✅ Automatic logging of payment failures
- ✅ Detailed error information stored in database
- ✅ Payment attempt history tracking
- ✅ Frontend integration for failure reporting

### Receipt/Invoice Generation
- ✅ Detailed invoices with GST breakdown
- ✅ Professional receipt format
- ✅ Customer and company details
- ✅ Item-wise billing
- ✅ Terms and conditions included

## Notes

- Amount is always in **paise** (₹1 = 100 paise)
- All payments are logged in MongoDB `payments` collection
- Payment signature verification is mandatory for security
- Mobile number is normalized and stored for user tracking

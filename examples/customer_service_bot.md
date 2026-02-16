# Customer Service Bot PRD

## Overview
An AI-powered customer service bot that helps users with orders and support.

Language: English
Channel: Voice
Phase: 1

## Feature F-01: Greeting and Identification

### Description
Greet the customer and identify them by their phone number.

### Flow (Audio)
1. Greet the customer with a welcome message
2. Ask for their phone number
3. Validate the phone number format
4. Look up customer in the CRM system

### Variables Used
- phone_number
- customer_id
- customer_name

### APIs Used
- lookup_customer

## Feature F-02: Order Tracking

### Description
Help customers track their order status.

### Flow (Audio)
1. Ask for the order number
2. Validate order number format
3. Call the order status API
4. Read the order status to the customer
5. Ask if they need anything else

### Variables Used
- order_number
- order_status

### APIs Used
- get_order_status

## Feature F-03: Return Request

### Description
Process return requests for customers.

### Flow (Audio)
1. Ask for the order number
2. Ask for the reason for return
3. Check return eligibility
4. If eligible, generate return label
5. Confirm return request

### Variables Used
- order_number
- return_reason
- return_eligible

### APIs Used
- check_return_eligibility
- create_return

## Feature F-04: Transfer to Agent

### Description
Transfer the customer to a human agent when needed.

### Flow (Audio)
1. Inform customer about transfer
2. Collect email for follow-up
3. Create support ticket
4. Transfer to agent queue

### Variables Used
- customer_email
- ticket_id

### APIs Used
- create_ticket

## Variables

| Name | Type | Description | Source |
|------|------|-------------|--------|
| phone_number | string | Customer phone number | collect |
| customer_id | string | Customer ID from CRM | tool |
| customer_name | string | Customer full name | tool |
| order_number | string | Order number to track | collect |
| order_status | string | Current order status | tool |
| return_reason | string | Reason for return | collect |
| return_eligible | boolean | Whether return is allowed | tool |
| customer_email | string | Customer email address | collect |
| ticket_id | string | Support ticket ID | tool |

## APIs

### lookup_customer
Method: POST
Endpoint: /api/crm/lookup
Description: Look up customer by phone number

### get_order_status
Method: GET
Endpoint: /api/orders/{order_number}/status
Description: Get order status by order number

### check_return_eligibility
Method: POST
Endpoint: /api/returns/check
Description: Check if order is eligible for return

### create_return
Method: POST
Endpoint: /api/returns/create
Description: Create a return request

### create_ticket
Method: POST
Endpoint: /api/support/tickets
Description: Create a support ticket

## Business Rules

| ID | Name | Condition | Action |
|----|------|-----------|--------|
| BR-01 | Working Hours | Outside 8:00-18:00 | Transfer to voicemail |
| BR-02 | Return Window | Order older than 30 days | Deny return request |
| BR-03 | VIP Customer | customer_id starts with VIP | Priority handling |

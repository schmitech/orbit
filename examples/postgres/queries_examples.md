# SQL Intent Query Examples

This document provides working examples for all available SQL intent templates in the customer orders database. **Updated with 25+ new advanced templates for comprehensive AI assistant capabilities.**

## Table of Contents
1. [Customer Search Queries](#customer-search-queries)
2. [Order Search Queries](#order-search-queries)
3. [Time-Based Queries](#time-based-queries)
4. [Amount-Based Queries](#amount-based-queries)
5. [Status-Based Queries](#status-based-queries)
6. [Geographic Queries](#geographic-queries)
7. [Analytics & Summary Queries](#analytics--summary-queries)
8. [Top/Bottom Rankings](#topbottom-rankings)
9. [🆕 Business Intelligence Queries](#-business-intelligence-queries)
10. [🆕 Advanced Analytics](#-advanced-analytics)
11. [🆕 Comparative Analysis](#-comparative-analysis)

---

## Customer Search Queries

### Find Orders by Customer Name
```
✓ Show me orders from customer John Smith
✓ What did Jane Doe order?
✓ Find all orders from customer Bob Johnson
✓ Orders placed by Alice Wilson
✓ Show me all orders from customer Mary Brown
✓ Customer Michael Davis orders
✓ Find customer Sarah Johnson's purchases
```

### Find Orders by Customer Name (Recent)
```
✓ Show me orders from John Smith in the last 3 days
✓ What did Jane Doe order this week?
✓ Find all orders from Bob Johnson within the last 7 days
✓ I'm looking for all orders from Shelia Olson within the last 3 days
```

### Find Orders by Customer ID
```
✓ Show orders for customer ID 5
✓ Find orders from customer #10
✓ Customer 123 orders
✓ Get purchases for customer number 7
✓ What did customer 1 buy last week?
```

### Find Customer by Email
```
✓ Find customer with email john@example.com
✓ Search for user@gmail.com
✓ Who has the email address sarah@company.com?
✓ Customer with email mike@domain.org
✓ Look up buyer@email.net
✓ Look up sescudero202507220947037871@oscuro.org please
```

---

## Order Search Queries

### Find Orders by Status
```
✓ Show me all pending orders
✓ What orders are still processing?
✓ Orders that have been delivered
✓ Show me the cancelled transactions
✓ Find all shipped packages
✓ Which orders are cancelled?
```

### Find Orders by Status and Time
```
✓ Find delivered orders from last week
✓ List cancelled orders from the last month
✓ Show shipped orders from yesterday
✓ Pending orders from the last 3 days
✓ Show processing orders from past 7 days
```

---

## Time-Based Queries

### List Customers by Time Period
```
✓ Who ordered from us last week?
✓ Which customers placed orders this month?
✓ Show me all customers who ordered in the last 7 days
✓ List customers who made purchases last week
✓ Who bought from us recently?
```

### Find Orders by Exact Date
```
✓ Show me orders on July 20th 2025
✓ Find orders from 25/07/2025
✓ Orders placed on 2025-07-20
✓ What orders were made on July 25, 2025?
✓ Show me what happened on 2025-07-25
```

### Find Orders by Date and Amount
```
✓ Show me orders above $500 on July 20th 2025
✓ Find orders over $1000 from 25/07/2025
✓ Orders above $100 placed on 2025-07-20
✓ Show orders under $50 on July 25, 2025
```

### Find New Customers
```
✓ Show me new customers from Aug 1 2025
✓ Who are the new customers this week?
✓ Find customers who registered in the last 7 days
✓ Show new customers from last month
✓ New customers who joined this month
```

### Find Inactive/Dormant Customers
```
✓ Show inactive customers
✓ Who hasn't ordered in 90 days?
✓ Find dormant customers
✓ Customers not buying recently
✓ Who hasn't ordered in 6 months?
```

---

## Amount-Based Queries

### Find High-Value Orders
```
✓ Find expensive orders above $1000
✓ Show orders worth more than $750
✓ Which orders exceeded $2000?
✓ Give me the premium orders over $1500
✓ Orders greater than $1200
```

### Find High-Value Orders (Time Period)
```
✓ Show me all orders over $500 from last month
✓ Find expensive orders above $1000
✓ List high-value orders from the last 30 days
✓ Orders worth more than $750 this week
✓ Which orders exceeded $2000 last quarter?
```

### Find Low-Value Orders
```
✓ Show me the tiny transactions below $25
✓ Find orders below $100
✓ Show all orders under $50
✓ Small purchases under $50
✓ Orders less than $25
```

### Find Low-Value Orders (Time Period)
```
✓ Show me all orders under $500 from last month
✓ Find cheap orders below $100
✓ List low-value orders from the last 30 days
✓ Find all orders below $500 in the last 20 days
```

### Find Orders Between Amounts
```
✓ Show orders between $100 and $500
✓ Find orders from $50 to $200
✓ Orders between $1000 and $5000
✓ Show me orders in the range of $100 to $300
```

### Find Biggest Orders (Recent)
```
✓ What are the biggest orders recently?
✓ Show me the largest orders this month
✓ Top orders by value from last week
✓ Highest value transactions lately
✓ Recent big orders
```

### Find Smallest Orders (Recent)
```
✓ What are the smallest orders recently?
✓ Show me the cheapest orders this month
✓ Bottom orders by value from last week
✓ Lowest value transactions lately
✓ Recent small orders
```

---

## Geographic Queries

### Find Orders by Customer City
```
✓ Show orders from customers in New York
✓ Find orders from customers located in Los Angeles
✓ What orders came from the city of Chicago?
✓ Orders from customers in San Francisco
✓ Show me orders from customers in the city of Boston
✓ Which customers from the city of Seattle ordered?
```

### Find Customers by City Who Ordered
```
✓ Which customers from Seattle ordered?
✓ Show me customers from New York who made purchases
✓ List customers from Chicago with orders
✓ Who are the customers from Miami that ordered?
✓ Boston customers who have purchased
```

### Find Orders by Shipping Country
```
✓ Show orders shipped to the United States
✓ Orders shipped to France
✓ Show deliveries to Germany
✓ Orders going to Japan
✓ Show me orders shipped to Canada
```

### Find International Orders
```
✓ Show me international shipments
✓ Orders shipped outside Canada
✓ International delivery orders
✓ Cross-border orders
✓ Show international orders only
```

### Find International Orders by Amount
```
✓ International orders over $200
✓ Show international orders above $500
✓ Cross-border orders over $100
✓ International shipments above $1000
✓ High-value international orders over $300
```

---

## Analytics & Summary Queries

### Calculate Customer Lifetime Value by ID
```
✓ What's the lifetime value of customer 123?
✓ How much has customer 456 spent in total?
✓ Show me the total revenue from customer 89
✓ Calculate customer 12's lifetime spending
✓ Customer 345 lifetime statistics
✓ What's the total spent by customer 4124?
✓ How much has customer 1001 spent?
✓ Customer 9999 total spending
```

### Calculate Customer Lifetime Value by Name
```
✓ What's the total spent by customer John Doe?
✓ How much has Maria Smith spent in total?
✓ Show me the lifetime value of Sarah Connor
✓ Calculate John Smith's total spending
✓ Total revenue from Michael Brown
```

### Customer Spending Analysis by ID
```
✓ What's the total spent by customer 4124?
✓ How much has customer 1001 spent?
✓ Customer 9999 total spending
✓ Show spending for customer 2050
✓ Customer 789 analytics
✓ Total from customer number 555
```

---

## Top/Bottom Rankings

### Find Top Buyers by Spending
```
✓ Show me the Top 5 buyers please
✓ Who are our top 10 customers?
✓ Find the biggest spenders
✓ Show me the top customers by spending
✓ Who are our best buyers?
✓ Top 5 customers by revenue
✓ Show me the top 3 spenders
```

---

## 🆕 Business Intelligence Queries

### Monthly Revenue Analysis
```
✓ Show me monthly revenue for this year
✓ What's our revenue trend by month?
✓ Monthly sales performance analysis
✓ Revenue growth by month
✓ How much revenue did we make each month?
✓ Monthly revenue report
```

### Daily Sales Summary
```
✓ Show me today's sales
✓ What were our sales yesterday?
✓ Daily sales for the past week
✓ How much did we sell today?
✓ Today's revenue summary
✓ Daily sales performance
✓ Show me sales for August 4th 2025
```

### Customer Order Frequency Analysis
```
✓ How often do customers order?
✓ Show me customer ordering patterns
✓ Customer purchase frequency analysis
✓ How many times do customers typically order?
✓ Show repeat customer behavior
✓ Customer ordering frequency breakdown
```

### Top Selling Periods
```
✓ What are our busiest days?
✓ When do we get the most orders?
✓ Show me peak ordering times
✓ What days have the highest sales?
✓ Busiest days of the week
✓ Peak sales periods
```

### Revenue by Customer Segment
```
✓ How much revenue comes from each customer type?
✓ Revenue breakdown by customer segment
✓ Show revenue from high vs low value customers
✓ Customer segment revenue analysis
✓ Which customer groups generate the most revenue?
```

### Order Completion Rate Analysis
```
✓ What's our order completion rate?
✓ How many orders get cancelled?
✓ Order status breakdown
✓ Show me fulfillment success rate
✓ Order processing statistics
✓ How many orders complete successfully?
```

### Average Order Value Trends
```
✓ How has our average order value changed?
✓ AOV trends over time
✓ Is our average order value going up or down?
✓ Show me average order value by month
✓ Average order value analysis
✓ AOV performance trends
```

### Customer Lifetime Value Distribution
```
✓ What's the distribution of customer values?
✓ How are customer lifetime values spread?
✓ Customer value distribution analysis
✓ Show me customer value ranges
✓ Customer lifetime value breakdown
```

### Seasonal Sales Patterns
```
✓ What are our seasonal sales patterns?
✓ Do we have seasonal trends?
✓ Sales by season analysis
✓ When do we sell the most?
✓ Seasonal revenue patterns
✓ Show me sales by quarter
```

---

## 🆕 Advanced Analytics

### Customer Retention Analysis
```
✓ How many customers come back to buy again?
✓ What's our customer retention rate?
✓ Show me repeat customer statistics
✓ Customer retention analysis
✓ How many customers make a second purchase?
✓ Repeat purchase behavior
```

### Customer Churn Risk Analysis
```
✓ Which customers might stop buying?
✓ Show me customers at risk of leaving
✓ Customer churn risk analysis
✓ Who hasn't ordered in a while?
✓ Identify at-risk customers
✓ Customers likely to churn
```

### Purchase Pattern Analysis
```
✓ What are our customers' buying patterns?
✓ How often do customers typically order?
✓ Customer purchase behavior analysis
✓ Show me buying habits
✓ Purchase pattern insights
✓ Customer ordering behavior
```

### Order Value Distribution Analysis
```
✓ What's the distribution of our order values?
✓ How are order amounts spread out?
✓ Order value analysis
✓ Show me order size patterns
✓ Order amount distribution
✓ What are our typical order sizes?
```

### Geographical Sales Analysis
```
✓ How do sales vary by location?
✓ Geographical sales performance
✓ Sales by region analysis
✓ Which locations perform best?
✓ Geographic revenue breakdown
✓ Sales performance by country and city
```

### Customer Acquisition Analysis
```
✓ How many new customers are we getting?
✓ Customer acquisition trends
✓ New customer analysis
✓ Show me customer growth
✓ How fast are we acquiring customers?
✓ New customer acquisition rate
```

### Order Time Analysis
```
✓ What time of day do people order most?
✓ When are orders typically placed?
✓ Order timing analysis
✓ Peak ordering hours
✓ What hours are busiest for orders?
✓ Daily order patterns
```

### Customer Value Percentiles
```
✓ Who are the top 10% of customers by value?
✓ Show me customer value percentiles
✓ Top customer performance analysis
✓ Customer value distribution by percentile
✓ Who are our highest value customers?
✓ Top performer customer analysis
```

---

## 🆕 Comparative Analysis

### Compare Periods Revenue
```
✓ Compare this month's sales to last month
✓ How do sales this quarter compare to last quarter?
✓ Show me year over year revenue comparison
✓ Compare revenue this week vs last week
✓ Month over month sales comparison
✓ Revenue comparison between periods
✓ Sales growth from last month to this month
```

### Compare Customer Segments Performance
```
✓ Compare high value vs regular customers
✓ How do VIP customers compare to others?
✓ Performance comparison between customer segments
✓ Compare new vs returning customers
✓ VIP vs regular customer analysis
✓ Customer segment performance comparison
```

### Geographic Performance Comparison
```
✓ Compare sales between countries
✓ Which cities perform better?
✓ International vs domestic sales comparison
✓ Geographic performance comparison
✓ Compare revenue by region
✓ City performance comparison
```

### Order Status Performance Comparison
```
✓ Compare order completion rates
✓ How do our fulfillment rates compare over time?
✓ Order status performance comparison
✓ Success rate comparison between periods
✓ Fulfillment performance analysis
✓ Compare delivery success rates
```

### Customer Behavior Before/After Comparison
```
✓ How did customer behavior change after July 1st?
✓ Compare customer patterns before and after a specific date
✓ Customer behavior comparison before/after date
✓ How did buying patterns change after July 15?
✓ Before and after customer analysis
```

### Weekly Performance Trends
```
✓ How do our weekly sales compare?
✓ Weekly performance comparison
✓ Show me week over week trends
✓ Weekly sales trend analysis
✓ Compare recent weeks performance
✓ Weekly revenue comparison
```

### High vs Low Value Order Comparison
```
✓ Compare high value vs low value orders
✓ What's different about expensive vs cheap orders?
✓ High vs low order value analysis
✓ Expensive order characteristics comparison
✓ Compare big vs small orders
✓ Order value segment comparison
```

---

## Tips for Best Results

1. **Customer Names**: Always use full names when searching (e.g., "John Smith" not just "John")
2. **Dates**: Use formats like "July 20th 2025", "2025-07-20", or "07/20/2025"
3. **Amounts**: Include dollar signs and be specific (e.g., "$500", "$1000")
4. **Time Periods**: Be specific with time ranges (e.g., "last 7 days", "last month", "past 30 days")
5. **Status Values**: Use exact status terms: pending, processing, shipped, delivered, cancelled
6. **Cities**: Use proper city names with correct spelling
7. **Email Addresses**: Include the full email address with @ symbol

## Common Parameter Patterns

- **days_back**: "last 7 days", "past 30 days", "last month", "this week"
- **min_amount/max_amount**: "$100", "$500", "$1000"
- **customer_name**: Full names like "John Smith", "Jane Doe"
- **customer_id**: Numeric IDs like "123", "456", "#789"
- **status**: "pending", "processing", "shipped", "delivered", "cancelled"
- **city**: "New York", "Los Angeles", "Chicago", "San Francisco"
- **limit**: "top 5", "top 10", "show me 20"

## Troubleshooting

If a query doesn't work:
1. Check if you're using the exact parameter format expected
2. Ensure customer names are complete and properly spelled
3. Use the date format YYYY-MM-DD for exact dates
4. Include currency symbols for amounts
5. Be specific about time periods using "days" terminology
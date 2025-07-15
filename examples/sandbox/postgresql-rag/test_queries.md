# 100 Test Queries for PostgreSQL RAG System

This document contains 100 diverse test queries to thoroughly test the conversational demo system. The queries are organized by category and cover all supported template types, edge cases, and natural language variations.

## Database Schema Reference

**Customers Table:**
- `id` (SERIAL PRIMARY KEY)
- `name` (VARCHAR(255))
- `email` (VARCHAR(255) UNIQUE)
- `phone` (VARCHAR(20))
- `address` (TEXT)
- `city` (VARCHAR(100))
- `country` (VARCHAR(100))
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

**Orders Table:**
- `id` (SERIAL PRIMARY KEY)
- `customer_id` (INTEGER, FOREIGN KEY)
- `order_date` (DATE)
- `total` (DECIMAL(10,2))
- `status` (VARCHAR(50)) - values: pending, processing, shipped, delivered, cancelled
- `shipping_address` (TEXT)
- `payment_method` (VARCHAR(50)) - values: credit_card, debit_card, paypal, bank_transfer, cash
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

---

## 🛍️ Customer Queries (1-20)

### Basic Customer Lookups
1. "What did customer 1 buy last week?"
2. "Show me orders from Maria Smith"
3. "Find orders for John Doe"
4. "What did Jessica Johnson order?"
5. "Show orders from customer Anthony Green"
6. "List orders for Teresa Lyons"
7. "Find all orders by Thomas Howell"
8. "I'm looking for purchases made by Sarah Connor"
9. "Can you check what Robert Williams bought?"
10. "Orders placed by Jennifer Lopez please"

### Customer by ID
11. "Show me recent orders for customer 123"
12. "What has customer 456 ordered recently?"
13. "List the last 10 orders for customer 42"
14. "What has customer 5 ordered recently?"
15. "Show customer 1's recent activity"
16. "Can you pull up what customer 89 purchased this month?"
17. "I need to see customer 456's latest purchases"
18. "What's been ordered by customer 12 lately?"
19. "Recent shopping history for customer 234"
20. "Display the latest transactions for customer 567"

---

## 💰 Order Value Queries (21-40)

### High Value Orders
21. "Show me all orders over $500 from last month"
22. "Find expensive orders above $1000"
23. "List high-value orders from the last 30 days"
24. "What are the biggest orders recently?"
25. "Show orders worth more than $750"
26. "Which orders exceeded $2000?"
27. "Give me the premium orders over $1500"
28. "Large transactions above $800 please"
29. "Find all big ticket items over $600"
30. "Orders greater than $1200"

### Low Value Orders
31. "Show me all orders under $500 from last month"
32. "Find cheap orders below $100"
33. "List low-value orders from the last 30 days"
34. "What are the smallest orders recently?"
35. "Show orders worth less than $250"
36. "Find all orders below $500 in the last 20 days"
37. "Small purchases under $50"
38. "Budget orders less than $75"
39. "Show me the tiny transactions below $25"
40. "Orders smaller than $150"

### Order Ranges
41. "Show orders between $100 and $500"
42. "Find purchases from $50 to $200"
43. "Orders in the $300-$800 range"
44. "What orders fall between $150 and $600?"
45. "Show me mid-range orders $200-$700"
46. "Transactions between $75 and $300 please"
47. "Orders priced from $400 to $1000"
48. "Find orders in the $100 to $250 bracket"
49. "Show me orders between $500 and $1500"
50. "Orders in the $50 to $300 range"

---

## 📦 Order Status Queries (51-65)

### Status-Specific Queries
51. "Show me all pending orders"
52. "Find delivered orders from last week"
53. "List cancelled orders from the last month"
54. "What orders are still processing?"
55. "Show shipped orders from yesterday"
56. "Which orders are waiting to be processed?"
57. "Orders that have been delivered"
58. "Show me the cancelled transactions"
59. "What's in pending status?"
60. "Find all shipped packages"
61. "Orders currently being processed"
62. "Show completed deliveries"
63. "Which orders are cancelled?"
64. "Find processing orders from this week"
65. "Show me all delivered orders from last month"

---

## 📊 Summary & Analytics Queries (66-80)

### Customer Summaries
66. "What's the lifetime value of customer 123?"
67. "How much has customer 456 spent in total?"
68. "Show me the total revenue from customer 89"
69. "Calculate customer 12's lifetime spending"
70. "What's customer 567's total purchase amount?"
71. "How valuable is customer 234 to us?"
72. "Total sales to customer 890"
73. "Customer 345 lifetime statistics"
74. "Give me a summary for customer 123"
75. "What's the total spent by customer John Doe?"

### Sales Summaries
76. "What were yesterday's sales?"
77. "Show me today's revenue"
78. "Sales summary for last Monday"
79. "How much did we sell on 2024-12-25?"
80. "Daily sales report for this week"

---

## 🌍 Location-Based Queries (81-90)

### City Queries
81. "Show orders from New York customers"
82. "Find orders from customers in Los Angeles"
83. "What orders came from Chicago?"
84. "Orders from San Francisco customers"
85. "Show me orders from Boston"
86. "Which customers from Seattle ordered?"
87. "Dallas customer orders"
88. "Find Miami purchases"
89. "Orders originating from Denver"
90. "Show Houston customer transactions"

### Country Queries
91. "Show orders from USA"
92. "Canadian customer orders"
93. "What did UK customers buy?"
94. "Orders from customers in France"
95. "Show German customer purchases"
96. "Find all orders from Australia"
97. "Mexican customer transactions"
98. "Orders coming from Japan"
99. "Show me Brazil purchases"
100. "Indian customer orders please"

---

## 💳 Payment Method Queries (101-110)

### Payment-Specific Queries
101. "Show me orders paid with credit card"
102. "Find PayPal orders from last month"
103. "What orders used bank transfer?"
104. "Show cash payments"
105. "Credit card orders analysis"
106. "How many debit card transactions?"
107. "Orders paid via PayPal"
108. "Bank transfer purchases"
109. "Show me all cash sales"
110. "Which orders used credit cards?"

---

## 📈 Trending & Analytics Queries (111-125)

### Top Customers
111. "Who are our top 10 customers?"
112. "Show me the biggest spenders"
113. "Which customers order the most?"
114. "Top customers by revenue"
115. "Best customers list"
116. "Who spends the most money?"
117. "Highest value customers"
118. "VIP customer list"
119. "Show our most valuable customers"
120. "Top 20 buyers"

### New Customers
121. "Show me new customers from this week"
122. "Who are our newest customers?"
123. "Recent first-time buyers"
124. "New customer acquisitions"
125. "First-time purchasers this month"

---

## 🔍 Search & Lookup Queries (126-135)

### Email Search
126. "Find customer with email john@example.com"
127. "Search for user@gmail.com"
128. "Who has the email address sarah@company.com?"
129. "Customer with email mike@domain.org"
130. "Look up buyer@email.net"

### Inactive Customers
131. "Show inactive customers"
132. "Who hasn't ordered in 90 days?"
133. "Find dormant customers"
134. "Customers not buying recently"
135. "Show me who stopped ordering"

---

## 🌐 International Shipping Queries (136-150)

### International Orders
136. "Show orders shipped to the United States"
137. "Orders delivered to European countries"
138. "International orders over $200"
139. "Shipping to Asian countries"
140. "Canadian customers shipping abroad"
141. "Orders with international shipping addresses"
142. "Show me international shipments"
143. "Orders shipped outside Canada"
144. "International delivery orders"
145. "Cross-border orders"

### Revenue by Destination
146. "Revenue by shipping destination"
147. "Which countries order the most?"
148. "Sales by destination country"
149. "International revenue breakdown"
150. "Revenue from different countries"

---

## 🔧 Edge Cases & Complex Queries (151-170)

### Complex Combinations
151. "Show me high-value orders from Toronto customers paid with credit card"
152. "Find cancelled orders over $1000 from last month"
153. "International orders under $500 paid via PayPal"
154. "Show pending orders from our top customers"
155. "Find orders between $200-$800 from Canadian customers"
156. "Credit card orders from New York over $750"
157. "Show me delivered orders from international customers"
158. "Find cash payments from customers in Los Angeles"
159. "Orders from inactive customers over $1000"
160. "Show me new customers who paid with bank transfer"

### Time-Based Complex Queries
161. "What did our top customers buy last week?"
162. "Show me international orders from the past 30 days over $500"
163. "Find cancelled orders from yesterday paid with credit card"
164. "Orders from Toronto customers in the last 7 days"
165. "Show me pending orders from this month over $1000"
166. "Find PayPal orders from last week under $200"
167. "International shipments from the past 14 days"
168. "Show me cash payments from today"
169. "Orders from new customers in the last 30 days"
170. "Find delivered orders from last month paid with debit card"

---

## 🎯 Natural Language Variations (171-190)

### Conversational Queries
171. "Can you tell me what customer 123 has been buying lately?"
172. "I'm curious about Maria Smith's recent purchases"
173. "What's the deal with all these pending orders?"
174. "Show me the big spenders from last month"
175. "Who are our most loyal customers?"
176. "I need to see what's happening with our international sales"
177. "Can you pull up the orders that are causing us trouble?"
178. "What's the story with our payment methods?"
179. "Show me who's been quiet lately"
180. "I want to see our best performing customers"

### Question Variations
181. "Which orders are over $500?"
182. "What orders came from Toronto?"
183. "How many orders are pending?"
184. "Who ordered from us last week?"
185. "What's the status of our recent orders?"
186. "Which customers are spending the most?"
187. "What payment methods are people using?"
188. "How are our international orders doing?"
189. "What's the average order value?"
190. "Who hasn't ordered in a while?"

---

## 🔍 Specific Parameter Tests (191-200)

### Amount Thresholds
191. "Show me orders over $1"
192. "Find orders under $1000000"
193. "Orders between $0.01 and $999999.99"
194. "Show me orders exactly $500"
195. "Find orders over $0"

### Time Periods
196. "Show me orders from the last 1 day"
197. "Find orders from the past 365 days"
198. "Orders from yesterday"
199. "Show me today's orders"
200. "Find orders from this year"

---

## 🧪 Testing Instructions

### Running the Tests

1. **Start the conversational demo:**
   ```bash
   cd examples/sandbox/postgresql-rag
   python conversational_demo.py
   ```

2. **Test Categories:**
   - Run queries 1-20 to test basic customer functionality
   - Run queries 21-50 to test order value filtering
   - Run queries 51-65 to test status filtering
   - Run queries 66-80 to test summary analytics
   - Run queries 81-100 to test location-based queries
   - Run queries 101-110 to test payment method filtering
   - Run queries 111-125 to test trending analytics
   - Run queries 126-135 to test search functionality
   - Run queries 136-150 to test international shipping
   - Run queries 151-170 to test complex combinations
   - Run queries 171-190 to test natural language variations
   - Run queries 191-200 to test edge cases

### Expected Behaviors

- **Successful queries** should return relevant results with proper formatting
- **Failed queries** should provide helpful error messages or suggestions
- **Parameter extraction** should work correctly for various input formats
- **Template matching** should select appropriate templates for each query type
- **Plugin integration** should enhance results with additional insights
- **Response generation** should be conversational and informative

### Validation Checklist

- [ ] All customer ID queries work with numeric IDs
- [ ] Customer name queries work with partial name matching
- [ ] Amount filters work with various currency formats
- [ ] Date/time filters work with natural language
- [ ] Status filters work with all valid statuses
- [ ] Payment method filters work with all valid methods
- [ ] Location queries work with city and country names
- [ ] Summary queries return aggregated statistics
- [ ] Complex queries combine multiple filters correctly
- [ ] Edge cases handle gracefully with appropriate responses
- [ ] Natural language variations are understood correctly
- [ ] Plugin enhancements are applied where appropriate

---

## 📝 Notes

- These queries are designed to test the full range of functionality supported by the query templates
- Some queries may return no results depending on the actual data in your database
- The system should handle both successful and failed queries gracefully
- Plugin functionality may enhance results with additional business insights
- All queries should be processed through the conversational interface for natural language understanding 
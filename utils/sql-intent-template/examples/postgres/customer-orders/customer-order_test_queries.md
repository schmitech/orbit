# Customer-Order System - Test Queries

This document provides test queries for the customer-order system database schema. These queries will be used to generate SQL intent templates for the Intent PostgreSQL retriever.

## Customer Queries

### Search by Name
1. "Find customers named John"
2. "Show me customers with 'Smith' in their name"
3. "Search for customers named 'Johnson'"
4. "Find customers with 'Brown' in their name"
5. "Show me customers named 'Wilson'"
6. "Search for customers with 'Davis' in their name"
7. "Find customers named 'Miller'"
8. "Show me customers with 'Garcia' in their name"

### Search by Email
9. "Find customer with email john@example.com"
10. "Show me customers with @gmail.com email addresses"
11. "Search for customers with @company.com emails"
12. "Find customers with email containing 'test'"
13. "Show me customers with @yahoo.com email addresses"
14. "Search for customers with email containing 'admin'"
15. "Find customers with @outlook.com email addresses"
16. "Show me customers with email containing 'support'"

### Search by Phone
17. "Find customers with phone number 555-1234"
18. "Show me customers with phone numbers starting with 555"
19. "Search for customers with phone numbers containing 123"
20. "Find customers with phone numbers ending in 0000"
21. "Show me customers with phone numbers starting with 800"
22. "Search for customers with phone numbers containing 999"

### Search by Location
23. "Find customers from New York"
24. "Show me customers from California"
25. "Search for customers from Texas"
26. "Find customers from Chicago"
27. "Show me customers from Los Angeles"
28. "Search for customers from Miami"
29. "Find customers from Seattle"
30. "Show me customers from Boston"

### Search by Country
31. "Find customers from USA"
32. "Show me customers from Canada"
33. "Search for customers from Mexico"
34. "Find customers from United Kingdom"
35. "Show me customers from Germany"
36. "Search for customers from France"
37. "Find customers from Australia"
38. "Show me customers from Japan"

### Search by Creation Date
39. "Show me customers created this year"
40. "Find customers created last month"
41. "List customers created in the last 30 days"
42. "Show me customers created in 2024"
43. "Find customers created this week"
44. "Show me recent customers"
45. "List customers created yesterday"
46. "Show me customers created today"

## Order Queries

### Search by Order ID
47. "Find order with ID 12345"
48. "Show me order 67890"
49. "Search for order 11111"
50. "Find order 99999"

### Search by Customer
51. "Show me orders for customer John Smith"
52. "Find orders by customer with email john@example.com"
53. "List orders for customer ID 1"
54. "Show me orders for customer with phone 555-1234"
55. "Find orders by customer from New York"
56. "List orders for customer named Johnson"

### Search by Order Date
57. "Show me orders from today"
58. "Find orders from yesterday"
59. "List orders from this week"
60. "Show me orders from last month"
61. "Find orders from this year"
62. "List orders from 2024"
63. "Show me orders from January"
64. "Find orders from last quarter"

### Search by Order Status
65. "Show me pending orders"
66. "Find completed orders"
67. "List cancelled orders"
68. "Show me shipped orders"
69. "Find processing orders"
70. "List delivered orders"
71. "Show me returned orders"
72. "Find refunded orders"

### Search by Order Total
73. "Show me orders over $100"
74. "Find orders under $50"
75. "List orders between $50 and $100"
76. "Show me orders over $500"
77. "Find orders under $25"
78. "List orders between $100 and $200"
79. "Show me expensive orders over $1000"
80. "Find cheap orders under $10"

### Search by Payment Method
81. "Show me orders paid with credit card"
82. "Find orders paid with PayPal"
83. "List orders paid with cash"
84. "Show me orders paid with bank transfer"
85. "Find orders paid with check"
86. "List orders paid with cryptocurrency"
87. "Show me orders paid with gift card"
88. "Find orders paid with Apple Pay"

### Search by Shipping Address
89. "Show me orders shipped to New York"
90. "Find orders shipped to California"
91. "List orders shipped to Texas"
92. "Show me orders shipped to Chicago"
93. "Find orders shipped to Los Angeles"
94. "List orders shipped to Miami"
95. "Show me orders shipped to Seattle"
96. "Find orders shipped to Boston"

## Complex Queries

### Multi-Criteria Searches
97. "Show me pending orders from New York customers"
98. "Find completed orders over $100 from California"
99. "List orders from this month paid with credit card"
100. "Show me orders from John Smith over $50"
101. "Find orders shipped to Chicago with status pending"
102. "List orders from Gmail users created this week"
103. "Show me orders over $200 from customers in Texas"
104. "Find orders paid with PayPal from last month"

### Customer Analytics
105. "How many customers do we have?"
106. "Show me the total number of customers by country"
107. "Find the most active customers by order count"
108. "List customers who haven't placed any orders"
109. "Show me customers with the highest order totals"
110. "Find customers who joined this year"
111. "List customers by city"
112. "Show me customer distribution by email domain"

### Order Analytics
113. "What's the total value of all orders?"
114. "Show me the average order value"
115. "Find the highest value order"
116. "List orders by status count"
117. "Show me total orders by month"
118. "Find the most popular payment method"
119. "List orders by shipping location"
120. "Show me order trends over time"

### Revenue Analysis
121. "What's our total revenue this year?"
122. "Show me revenue by month"
123. "Find revenue by customer country"
124. "List revenue by payment method"
125. "Show me revenue from completed orders only"
126. "Find revenue by customer city"
127. "List revenue trends over time"
128. "Show me revenue by order status"

### Customer Behavior
129. "Show me customers who placed multiple orders"
130. "Find customers with orders over $500"
131. "List customers who haven't ordered recently"
132. "Show me customers with pending orders"
133. "Find customers who cancelled orders"
134. "List customers by order frequency"
135. "Show me customers with high-value orders"
136. "Find customers who order frequently"

### Order Management
137. "Show me orders that need to be shipped"
138. "Find orders that are overdue"
139. "List orders requiring customer contact"
140. "Show me orders with payment issues"
141. "Find orders ready for processing"
142. "List orders awaiting confirmation"
143. "Show me orders that need refunds"
144. "Find orders with shipping problems"

### Geographic Analysis
145. "Show me orders by shipping country"
146. "Find orders by customer location"
147. "List orders by shipping city"
148. "Show me orders by customer country"
149. "Find orders by region"
150. "List orders by state"
151. "Show me orders by postal code"
152. "Find orders by time zone"

### Time-Based Analysis
153. "Show me orders from this quarter"
154. "Find orders from last quarter"
155. "List orders by day of week"
156. "Show me orders by hour of day"
157. "Find orders from weekends"
158. "List orders from weekdays"
159. "Show me orders from holidays"
160. "Find orders from business hours"

### Status Tracking
161. "Show me all pending orders"
162. "Find orders that are processing"
163. "List orders that are shipped"
164. "Show me orders that are delivered"
165. "Find orders that are cancelled"
166. "List orders that are returned"
167. "Show me orders that are refunded"
168. "Find orders with status issues"

### Payment Analysis
169. "Show me orders by payment method"
170. "Find orders with payment problems"
171. "List orders by payment status"
172. "Show me orders with failed payments"
173. "Find orders with successful payments"
174. "List orders by payment amount"
175. "Show me orders with payment disputes"
176. "Find orders with payment refunds"

### Customer Service
177. "Show me customers with support issues"
178. "Find customers who need follow-up"
179. "List customers with complaints"
180. "Show me customers with questions"
181. "Find customers who need assistance"
182. "List customers with special requests"
183. "Show me customers with feedback"
184. "Find customers with suggestions"

### Inventory Management
185. "Show me orders that are out of stock"
186. "Find orders with inventory issues"
187. "List orders requiring restocking"
188. "Show me orders with stock problems"
189. "Find orders with availability issues"
190. "List orders with supply problems"
191. "Show me orders with stock shortages"
192. "Find orders with inventory conflicts"

### Reporting Queries
193. "Generate a customer report"
194. "Create an order summary"
195. "Show me a sales report"
196. "Generate a revenue report"
197. "Create a customer analysis"
198. "Show me an order analysis"
199. "Generate a payment report"
200. "Create a shipping report"

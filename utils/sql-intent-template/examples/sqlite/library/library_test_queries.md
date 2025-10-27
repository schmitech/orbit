# Library Management System - Test Queries

This document provides test queries for the library management system database schema. These queries will be used to generate SQL intent templates for the Intent PostgreSQL retriever.

## Book Queries

### Search by Title
1. "Find books with 'Harry Potter' in the title"
2. "Show me books titled '1984'"
3. "Search for books containing 'Foundation'"
4. "Find books with 'Pride' in the title"
5. "Show me books with 'Shining' in the title"
6. "Search for books containing 'Murder'"
7. "Find books with 'Origin' in the title"
8. "Show me books containing 'Relativity'"

### Search by Author
9. "Find books by George Orwell"
10. "Show me books written by J.K. Rowling"
11. "Search for books by Isaac Asimov"
12. "Find books by Agatha Christie"
13. "Show me books written by Stephen King"
14. "Search for books by Jane Austen"
15. "Find books by Charles Darwin"
16. "Show me books written by Albert Einstein"

### Search by Category
17. "Show me all fiction books"
18. "Find science fiction books"
19. "List mystery books"
20. "Show me romance books"
21. "Find biography books"
22. "List history books"
23. "Show me science books"
24. "Find technology books"

### Search by Publisher
25. "Show me books from Penguin Random House"
26. "Find books published by HarperCollins"
27. "List books from Simon & Schuster"
28. "Show me Macmillan books"
29. "Find books from Hachette Book Group"

### Search by ISBN
30. "Find book with ISBN 978-0-452-28423-4"
31. "Show me book with ISBN 978-0-439-13959-7"
32. "Search for book with ISBN 978-0-553-29335-5"

### Search by Publication Date
33. "Show me books published in 1949"
34. "Find books from the 1990s"
35. "List books published before 1900"
36. "Show me recent books"
37. "Find books from the 19th century"
38. "List books published in 2023"

### Search by Availability
39. "Show me available books"
40. "Find books that are checked out"
41. "List books with copies available"
42. "Show me unavailable books"
43. "Find books with no available copies"

### Search by Price Range
44. "Show me books under $10"
45. "Find books between $10 and $15"
46. "List expensive books over $15"
47. "Show me cheap books under $5"

### Search by Language
48. "Show me English books"
49. "Find books in Spanish"
50. "List books in French"

## Member Queries

### Search by Name
51. "Find member John Smith"
52. "Show me member Sarah Johnson"
53. "Search for member Michael Brown"
54. "Find member Emily Davis"
55. "Show me member David Wilson"

### Search by Email
56. "Find member with email john.smith@email.com"
57. "Show me member with email sarah.johnson@email.com"
58. "Search for member with email michael.brown@email.com"

### Search by Membership Type
59. "Show me premium members"
60. "Find standard members"
61. "List student members"
62. "Show me senior members"
63. "Find all membership types"

### Search by Status
64. "Show me active members"
65. "Find inactive members"
66. "List all members"

### Search by Location
67. "Show me members from New York"
68. "Find members from Los Angeles"
69. "List members from Chicago"
70. "Show me members from Boston"
71. "Find members from Seattle"

## Loan Queries

### Search by Status
72. "Show me active loans"
73. "Find returned loans"
74. "List overdue loans"
75. "Show me lost books"
76. "Find all loan statuses"

### Search by Member
77. "Show me loans for John Smith"
78. "Find loans by Sarah Johnson"
79. "List loans for Michael Brown"
80. "Show me loans by Emily Davis"

### Search by Book
81. "Show me loans for '1984'"
82. "Find loans for 'Harry Potter'"
83. "List loans for 'Foundation'"
84. "Show me loans for 'Murder on the Orient Express'"

### Search by Date Range
85. "Show me loans from this month"
86. "Find loans from last week"
87. "List loans from 2024"
88. "Show me recent loans"
89. "Find loans from yesterday"

### Search by Due Date
90. "Show me loans due today"
91. "Find loans due this week"
92. "List overdue loans"
93. "Show me loans due soon"
94. "Find loans due next month"

### Search by Fine Amount
95. "Show me loans with fines"
96. "Find loans with no fines"
97. "List loans with high fines"
98. "Show me loans with overdue fines"

## Reservation Queries

### Search by Status
99. "Show me pending reservations"
100. "Find fulfilled reservations"
101. "List cancelled reservations"
102. "Show me expired reservations"

### Search by Member
103. "Show me reservations for John Smith"
104. "Find reservations by Sarah Johnson"
105. "List reservations for Michael Brown"

### Search by Book
106. "Show me reservations for '1984'"
107. "Find reservations for 'Foundation'"
108. "List reservations for 'Pride and Prejudice'"

### Search by Priority
109. "Show me high priority reservations"
110. "Find low priority reservations"
111. "List reservations by priority"

## Review Queries

### Search by Rating
112. "Show me 5-star reviews"
113. "Find 4-star reviews"
114. "List 3-star reviews"
115. "Show me low-rated reviews"
116. "Find highly rated books"

### Search by Book
117. "Show me reviews for '1984'"
118. "Find reviews for 'Harry Potter'"
119. "List reviews for 'Foundation'"
120. "Show me reviews for 'Murder on the Orient Express'"

### Search by Member
121. "Show me reviews by John Smith"
122. "Find reviews by Sarah Johnson"
123. "List reviews by Michael Brown"

### Search by Verification
124. "Show me verified reviews"
125. "Find unverified reviews"
126. "List all reviews"

## Author Queries

### Search by Name
127. "Find author George Orwell"
128. "Show me author J.K. Rowling"
129. "Search for author Isaac Asimov"
130. "Find author Agatha Christie"

### Search by Nationality
131. "Show me British authors"
132. "Find American authors"
133. "List German authors"
134. "Show me authors by nationality"

### Search by Birth Date
135. "Show me authors born in the 1900s"
136. "Find authors born before 1900"
137. "List authors born in the 20th century"
138. "Show me recent authors"

## Publisher Queries

### Search by Name
139. "Show me Penguin Random House"
140. "Find HarperCollins"
141. "List Simon & Schuster"
142. "Show me Macmillan Publishers"

### Search by Location
143. "Show me publishers from New York"
144. "Find publishers from USA"
145. "List publishers by country"

### Search by Founded Year
146. "Show me publishers founded in the 1900s"
147. "Find publishers founded before 1900"
148. "List publishers founded in the 2000s"

## Category Queries

### Search by Name
149. "Show me Fiction category"
150. "Find Science Fiction category"
151. "List Mystery category"
152. "Show me Romance category"

### Search by Parent Category
153. "Show me subcategories of Fiction"
154. "Find subcategories of Non-Fiction"
155. "List all categories"

## Complex Queries

### Multi-Criteria Searches
156. "Show me available science fiction books"
157. "Find books by British authors published before 1950"
158. "List mystery books with high ratings"
159. "Show me books with overdue loans"
160. "Find premium members with active loans"

### Statistical Queries
161. "How many books are in each category?"
162. "Show me the most popular books"
163. "Find the most active members"
164. "List books with the most reviews"
165. "Show me average rating by category"

### Overdue and Fines
166. "Show me all overdue books"
167. "Find members with overdue books"
168. "List total fines by member"
169. "Show me books with highest fines"

### Availability Analysis
170. "Show me books with no available copies"
171. "Find books with many reservations"
172. "List books that are always checked out"
173. "Show me books with low availability"

### Member Activity
174. "Show me most active borrowers"
175. "Find members with no loans"
176. "List members with overdue books"
177. "Show me members by loan count"

### Book Performance
178. "Show me most borrowed books"
179. "Find books with most reservations"
180. "List books with highest ratings"
181. "Show me books with most reviews"

### Time-based Analysis
182. "Show me loans from this year"
183. "Find books published this decade"
184. "List members who joined recently"
185. "Show me recent reviews"

### Search and Discovery
186. "Show me books similar to '1984'"
187. "Find books by authors like George Orwell"
188. "List books in the same category as 'Harry Potter'"
189. "Show me books with similar themes"

### Administrative Queries
190. "Show me all books needing attention"
191. "Find members with expired memberships"
192. "List books with missing information"
193. "Show me system statistics"
194. "Find books with data inconsistencies"
195. "List members with contact issues"

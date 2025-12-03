# HR Management System - Test Queries

This document provides test queries for the HR management database schema. These queries will be used to generate SQL intent templates for the Intent PostgreSQL retriever.

## Employee Management Queries

### Basic List All Employees
1. "Show me all employees"
2. "List all employees"
3. "Get all employees"
4. "Display employees"
5. "What employees do we have?"
6. "Find all employees"
7. "Show every employee"
8. "I need all employees"
9. "Get all available employees"
10. "Display entire employee list"
11. "Show complete employee database"
12. "Find all employee records"
13. "Show me the full employee list"
14. "Get all staff members"
15. "List all personnel"

### Search by Name (Text Filter)
16. "Find employees named John"
17. "Show me employees with name like Smith"
18. "Get employees whose name contains 'Brown'"
19. "Search for employees named Alice"
20. "Find all employees with 'Wilson' in their name"
21. "Show me employees named 'Johnson'"
22. "Get employees with name matching 'Davis'"
23. "Find employees with 'Miller' in their name"
24. "Show me employees named 'Garcia'"
25. "Search for employees containing 'Martinez'"

### Search by Email (Exact Match)
26. "Find employee with email john.doe@company.com"
27. "Show me the employee with email jane.smith@company.com"
28. "Get employee by email alice.brown@company.com"
29. "Who has email bob.johnson@company.com?"
30. "Find the employee with email charlie.wilson@company.com"

### Filter by Status
31. "Show me active employees"
32. "List all active staff"
33. "Get active employees"
34. "Find terminated employees"
35. "Show me employees on leave"
36. "List employees with status active"
37. "Get all active personnel"
38. "Show me current employees"
39. "Find employees who are active"
40. "List active team members"

## Department Queries

### List Departments
41. "Show me all departments"
42. "List all departments"
43. "Get department list"
44. "Display departments"
45. "What departments do we have?"
46. "Find all departments"
47. "Show me every department"
48. "Get all available departments"
49. "Display entire department list"
50. "Show complete department database"

### Find Department by Name
51. "Find Engineering department"
52. "Show me Sales department"
53. "Get Marketing department info"
54. "Find Human Resources department"
55. "Show me Finance department"
56. "Get Operations department"
57. "Find department named Engineering"
58. "Show me department called Sales"
59. "Get department with name Marketing"
60. "Find department Engineering"

### Filter by Location
61. "Show me departments in San Francisco"
62. "List departments in New York"
63. "Get departments located in Los Angeles"
64. "Find departments in Chicago"
65. "Show me departments in Boston"
66. "List departments in Seattle"
67. "Get departments in San Francisco"
68. "Find departments located in New York"
69. "Show me departments in Los Angeles"
70. "List departments in Chicago"

## Position/Job Title Queries

### List Positions
71. "Show me all positions"
72. "List all job titles"
73. "Get all positions"
74. "Display positions"
75. "What positions do we have?"
76. "Find all positions"
77. "Show me every position"
78. "Get all available positions"
79. "Display entire position list"
80. "Show complete position database"

### Find Position by Title
81. "Find Software Engineer position"
82. "Show me Sales Representative position"
83. "Get Marketing Manager position"
84. "Find Engineering Manager position"
85. "Show me HR Coordinator position"
86. "Get Finance Manager position"
87. "Find position named Software Engineer"
88. "Show me position called Sales Representative"
89. "Get position with title Marketing Manager"
90. "Find position Software Engineer"

### Filter Positions by Department
91. "Show me positions in Engineering"
92. "List jobs in Sales department"
93. "Get positions in Marketing"
94. "Find positions in Human Resources"
95. "Show me positions in Finance"
96. "List jobs in Operations"
97. "Get positions in Engineering department"
98. "Find jobs in Sales"
99. "Show me positions in Marketing department"
100. "List positions in Finance"

## Employee-Department Relationship Queries

### Employees by Department
101. "Show me employees in Engineering"
102. "List employees in Sales department"
103. "Get staff in Marketing"
104. "Find employees in Human Resources"
105. "Show me employees in Finance"
106. "List employees in Operations"
107. "Get employees in Engineering department"
108. "Find staff in Sales"
109. "Show me employees in Marketing department"
110. "List staff in Finance"

### Count Employees by Department
111. "How many employees per department?"
112. "Show me employee count by department"
113. "Get employee distribution by department"
114. "Count employees in each department"
115. "How many employees in Engineering?"
116. "Count employees from Sales"
117. "Show me employees per department"
118. "Get department employee counts"
119. "How many employees per location?"
120. "Show me department distribution"

## Employee-Position Relationship Queries

### Employees by Position
121. "Show me Software Engineers"
122. "List all Sales Representatives"
123. "Get employees with Manager position"
124. "Find Software Engineers"
125. "Show me Sales Representatives"
126. "List Marketing Managers"
127. "Get Engineering Managers"
128. "Find HR Coordinators"
129. "Show me Financial Analysts"
130. "List Operations Coordinators"

### Employees with Positions and Salaries
131. "Show me employees with their positions and salaries"
132. "List employees with job titles"
133. "Get staff with position assignments"
134. "Find employees with positions"
135. "Show me employee positions"
136. "List staff with their roles"
137. "Get employees and their titles"
138. "Find employees with job assignments"
139. "Show me staff positions"
140. "List employees with roles"

## Salary Queries

### Salary Range Filters
141. "Show me employees earning between 80000 and 120000"
142. "Find employees with salary 100000 to 150000"
143. "Get staff earning 50000 to 80000"
144. "List employees with salaries 120000 to 200000"
145. "Show me employees earning 60000 to 100000"
146. "Find staff with salary between 90000 and 130000"
147. "Get employees earning 75000 to 110000"
148. "List employees with salaries 85000 to 125000"
149. "Show me staff earning 55000 to 95000"
150. "Find employees with salary 110000 to 180000"

### Average Salary
151. "What's the average salary?"
152. "Get the mean salary"
153. "Calculate average employee salary"
154. "Show me average salary"
155. "What is the mean salary of all employees?"
156. "Get average salary of all employees"
157. "Show me mean employee salary"
158. "What's the average employee salary?"
159. "Calculate mean salary"
160. "Show me the average salary"

### Average Salary by Department
161. "What's the average salary by department?"
162. "Show me average salary per department"
163. "Get mean salary by department"
164. "Calculate average salary for each department"
165. "Show me department average salaries"
166. "Get average salary grouped by department"
167. "What's the mean salary per department?"
168. "Show me salary averages by department"
169. "Get average compensation by department"
170. "Calculate mean salary for departments"

### Salary Statistics
171. "Show me salary statistics"
172. "Get salary statistics"
173. "What are the salary stats?"
174. "Calculate salary statistics"
175. "Show me salary metrics"
176. "Get salary data summary"
177. "What's the salary breakdown?"
178. "Show me salary analytics"
179. "Get salary data analysis"
180. "What are the salary metrics?"

## Hire Date / Tenure Queries

### Recent Hires
181. "Show me employees hired in the last 30 days"
182. "List recent hires"
183. "Get employees hired this month"
184. "Find employees hired in the last week"
185. "Show me new employees"
186. "List employees hired recently"
187. "Get staff hired in the last 60 days"
188. "Find employees hired this year"
189. "Show me employees hired in the past month"
190. "List new hires"

### Employees by Hire Year
191. "Show me employees hired in 2020"
192. "List employees hired in 2021"
193. "Get staff hired in 2022"
194. "Find employees hired in 2019"
195. "Show me employees hired in 2018"
196. "List employees hired in 2023"
197. "Get staff hired in 2024"
198. "Find employees hired in 2017"
199. "Show me employees hired in 2016"
200. "List employees hired in 2015"

## Complex Queries

### Employee Full Profile
201. "Show me full profile for employee 1"
202. "Get complete employee information"
203. "Display employee profile"
204. "Show me employee details"
205. "Get full employee record"
206. "Display complete employee information"
207. "Show me employee profile with department and position"
208. "Get employee full details"
209. "Display employee complete profile"
210. "Show me all employee information"

### Department Roster
211. "Show me Engineering department roster"
212. "Get complete Sales team list"
213. "List all employees in Marketing with their positions"
214. "Show me Finance department roster"
215. "Get Operations team list"
216. "List all employees in Human Resources with their positions"
217. "Show me department roster for Engineering"
218. "Get complete team list for Sales"
219. "List Marketing department employees"
220. "Show me Finance team roster"

### Employees by Department and Position
221. "Find Software Engineers in Engineering"
222. "Show me Sales Representatives in Sales"
223. "Get Managers in Marketing"
224. "Find Engineers in Engineering department"
225. "Show me Analysts in Finance"
226. "Get Coordinators in Operations"
227. "Find Specialists in Marketing"
228. "Show me Representatives in Sales"
229. "Get Managers in Engineering"
230. "Find Coordinators in Human Resources"

### Multi-Criteria Queries
231. "Show me active employees in Engineering earning over 100000"
232. "Find Software Engineers in Engineering hired in 2020"
233. "Get Sales Representatives in Sales with salary between 50000 and 100000"
234. "List Marketing Managers in Marketing hired in the last year"
235. "Show me active employees in Finance earning over 80000"
236. "Find Engineers in Engineering with salary above 120000"
237. "Get active staff in Operations hired in 2021"
238. "List employees in Sales with position Sales Representative"
239. "Show me active employees in Human Resources earning between 60000 and 90000"
240. "Find Managers in Finance hired in the last 2 years"

## Aggregation and Analytics Queries

### Count Queries
241. "How many employees do we have?"
242. "Count all employees"
243. "What's the total number of employees?"
244. "How many employees are there?"
245. "Get the employee count"
246. "Show me total employees"
247. "What is the total employee count?"
248. "How many employees in the system?"
249. "Get total number of employees"
250. "Show me employee count"

### Department Statistics
251. "Show me department statistics"
252. "Get department analytics"
253. "What are the department stats?"
254. "Calculate department metrics"
255. "Show me department data summary"
256. "Get department breakdown"
257. "What's the department overview?"
258. "Show me department insights"
259. "Get department data analysis"
260. "What are the department metrics?"

### Position Statistics
261. "Show me position statistics"
262. "Get position analytics"
263. "What are the position stats?"
264. "Calculate position metrics"
265. "Show me position data summary"
266. "Get position breakdown"
267. "What's the position overview?"
268. "Show me position insights"
269. "Get position data analysis"
270. "What are the position metrics?"

## Summary and Overview Queries

### Employee Overview
271. "Show me all employee information"
272. "List complete employee database"
273. "Get all employee records"
274. "What employees do we have in total?"
275. "Show me the full employee database"
276. "List everything about employees"
277. "Get complete employee information"
278. "Display all employee data"
279. "Show me comprehensive employee list"
280. "Get all employee details"

### Department Overview
281. "Show me all department information"
282. "List complete department database"
283. "Get all department records"
284. "What departments do we have in total?"
285. "Show me the full department database"
286. "List everything about departments"
287. "Get complete department information"
288. "Display all department data"
289. "Show me comprehensive department list"
290. "Get all department details"

### Position Overview
291. "Show me all position information"
292. "List complete position database"
293. "Get all position records"
294. "What positions do we have in total?"
295. "Show me the full position database"
296. "List everything about positions"
297. "Get complete position information"
298. "Display all position data"
299. "Show me comprehensive position list"
300. "Get all position details"

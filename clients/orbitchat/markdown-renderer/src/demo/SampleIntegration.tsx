import { useState } from 'react';
import { MarkdownRenderer, preprocessMarkdown, containsMathNotation } from '../index';

/**
 * Sample integration component showing how to use the markdown-renderer
 * in a real application context
 */
export function SampleIntegration() {
  const [messages] = useState([
    {
      id: '1',
      content: 'How do I calculate the area of a circle?',
      role: 'user'
    },
    {
      id: '2',
      content: `The area of a circle is calculated using the formula:

$$A = \\pi r^2$$

Where:
- $A$ is the area
- $r$ is the radius
- $\\pi$ is approximately 3.14159

For example, if the radius is 5 units:
$$A = \\pi \\times 5^2 = \\pi \\times 25 \\approx 78.54 \\text{ square units}$$

You can also use the diameter ($d = 2r$):
$$A = \\frac{\\pi d^2}{4}$$`,
      role: 'assistant'
    },
    {
      id: '3',
      content: 'What about the cost if it\'s $5 per square unit?',
      role: 'user'
    },
    {
      id: '4',
      content: `If the cost is $5 per square unit and the area is approximately 78.54 square units:

**Total Cost** = Area × Price per unit
**Total Cost** = 78.54 × $5 = $392.70

So it would cost $392.70 to cover a circular area with radius 5 units at $5 per square unit.

Here's a table showing costs for different radii:

| Radius | Area ($\\pi r^2$) | Cost at $5/unit² |
|--------|------------------|------------------|
| 1      | 3.14            | $15.71          |
| 3      | 28.27           | $141.37         |
| 5      | 78.54           | $392.70         |
| 10     | 314.16          | $1,570.80       |`,
      role: 'assistant'
    }
  ]);

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '20px' }}>
      <h2>Sample Chat Integration</h2>
      <div style={{ 
        border: '1px solid #e0e0e0', 
        borderRadius: '8px', 
        padding: '20px',
        backgroundColor: '#f9f9f9'
      }}>
        {messages.map((message) => (
          <div
            key={message.id}
            style={{
              marginBottom: '20px',
              display: 'flex',
              justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start'
            }}
          >
            <div
              style={{
                maxWidth: '70%',
                padding: '12px 16px',
                borderRadius: '12px',
                backgroundColor: message.role === 'user' ? '#007bff' : '#ffffff',
                color: message.role === 'user' ? '#ffffff' : '#333333',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
              }}
            >
              {message.role === 'assistant' ? (
                <MarkdownRenderer content={message.content} />
              ) : (
                <div>{message.content}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '40px' }}>
        <h3>Utility Functions Demo</h3>
        
        <div style={{ 
          backgroundColor: '#f0f0f0', 
          padding: '15px', 
          borderRadius: '8px',
          marginTop: '10px'
        }}>
          <h4>preprocessMarkdown()</h4>
          <p>Input: <code>"The price is $100 and the formula is $x^2$"</code></p>
          <p>Output: <code>{preprocessMarkdown("The price is $100 and the formula is $x^2$")}</code></p>
        </div>

        <div style={{ 
          backgroundColor: '#f0f0f0', 
          padding: '15px', 
          borderRadius: '8px',
          marginTop: '10px'
        }}>
          <h4>containsMathNotation()</h4>
          <p>Text with math ($x^2$): <strong>{containsMathNotation("Here is $x^2$") ? 'Yes' : 'No'}</strong></p>
          <p>Text with currency ($100): <strong>{containsMathNotation("Price is $100") ? 'Yes' : 'No'}</strong></p>
          <p>Text with display math: <strong>{containsMathNotation("$$\\int_0^1 x dx$$") ? 'Yes' : 'No'}</strong></p>
        </div>
      </div>
    </div>
  );
}
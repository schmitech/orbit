import { MarkdownRenderer, preprocessMarkdown } from '../index';
import { MinimalMathTest } from './MinimalMathTest';

export function DebugMath() {
  const testContent = `For example, if the radius is 5 units:

$$A = \\pi \\times 5^2 = \\pi \\times 25 \\approx 78.54 \\text{ square units}$$`;
  
  const simpleTest = `The formula is $x^2 + y^2 = z^2$`;
  const displayTest = `Display math:
$$\\int_0^1 x dx = \\frac{1}{2}$$`;
  
  const processed = preprocessMarkdown(testContent);
  
  return (
    <div style={{ padding: '20px' }}>
      <h2>Math Debug</h2>
      
      <div style={{ marginBottom: '20px' }}>
        <h3>Original:</h3>
        <pre style={{ background: '#f5f5f5', padding: '10px' }}>
          {testContent}
        </pre>
      </div>
      
      <div style={{ marginBottom: '20px' }}>
        <h3>Preprocessed:</h3>
        <pre style={{ background: '#f5f5f5', padding: '10px' }}>
          {processed}
        </pre>
      </div>
      
      <div>
        <h3>Rendered (Original):</h3>
        <div style={{ border: '1px solid #ddd', padding: '10px', background: 'white' }}>
          <MarkdownRenderer content={testContent} />
        </div>
      </div>
      
      <div style={{ marginTop: '20px' }}>
        <h3>Simple Math Test:</h3>
        <div style={{ border: '1px solid #ddd', padding: '10px', background: 'white' }}>
          <MarkdownRenderer content={simpleTest} />
        </div>
      </div>
      
      <div style={{ marginTop: '20px' }}>
        <h3>Display Math Test:</h3>
        <div style={{ border: '1px solid #ddd', padding: '10px', background: 'white' }}>
          <MarkdownRenderer content={displayTest} />
        </div>
      </div>
      
      <hr style={{ margin: '40px 0', borderTop: '2px solid #ddd' }} />
      
      <MinimalMathTest />
    </div>
  );
}
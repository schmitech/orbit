import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

export function MinimalMathTest() {
  const simpleInline = 'The formula is $x^2 + y^2 = z^2$ here.';
  const simpleDisplay = `Display math:

$$E = mc^2$$`;

  return (
    <div style={{ padding: '20px' }}>
      <h2>Minimal Math Test (No Preprocessing)</h2>
      
      <div style={{ marginBottom: '20px' }}>
        <h3>Inline Math:</h3>
        <div style={{ border: '1px solid #ddd', padding: '10px', background: 'white' }}>
          <ReactMarkdown
            remarkPlugins={[[remarkMath, { singleDollarTextMath: true }]]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
          >
            {simpleInline}
          </ReactMarkdown>
        </div>
      </div>
      
      <div style={{ marginBottom: '20px' }}>
        <h3>Display Math:</h3>
        <div style={{ border: '1px solid #ddd', padding: '10px', background: 'white' }}>
          <ReactMarkdown
            remarkPlugins={[[remarkMath, { singleDollarTextMath: true }]]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
          >
            {simpleDisplay}
          </ReactMarkdown>
        </div>
      </div>
      
      <div style={{ marginTop: '20px' }}>
        <h3>Raw Content (for comparison):</h3>
        <pre style={{ background: '#f5f5f5', padding: '10px' }}>
          {simpleInline}
        </pre>
        <pre style={{ background: '#f5f5f5', padding: '10px' }}>
          {simpleDisplay}
        </pre>
      </div>
    </div>
  );
}